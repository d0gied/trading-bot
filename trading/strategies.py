from loguru import logger
from requests import session

from db.models import ShareStrategy
from .client import InvestClient, get_client
from .transaction import Transaction, PostOrderResponse
from db.strategies import get_share_strategies
from db.orders import Order, get_orders
from db import Connection
from aiogram import Bot

from trading.orders import Quotation
from config import Config

config = Config()  # type: ignore

bot = Bot(token=config.BOT_TOKEN)


async def send_message(message: str):
    for admin in config.ADMIN_IDS:
        await bot.send_message(admin, message)


async def on_update(order_id: str):
    async with get_client() as client:
        with Connection() as db:
            order = get_orders(db, order_id=order_id)[0]
            if not order:
                raise ValueError(f"Order {order_id} not found")
            share = await client.get_share_by_figi(str(order.figi))
            if share is None:
                raise ValueError(f"Share {order.figi} not found")

            should_add_money = (
                str(order.direction).lower() == "buy"
                and str(order.status).lower() in ["cancelled", "rejected"]
            ) or (
                str(order.direction).lower() == "sell"
                and str(order.status).lower() in ["fill"]
            )
            if not should_add_money:
                return

            extra_balance = Quotation(int(order.price_units), int(order.price_nanos)) * int(  # type: ignore
                order.lots  # type: ignore
            )
            ticker = share.ticker
            strategy = get_share_strategies(db, 1, ticker)
            if not strategy:
                return
            strategy = strategy[0]
            strategy.free_capital = float(strategy.free_capital) + extra_balance.amount  # type: ignore
            db.commit()
            logger.debug(f"Returned {extra_balance} to free capital")


async def tick():
    # async with get_client() as client:
    #     await client.update_orders(
    #         on_cancel=on_update,
    #         on_reject=on_update,
    #     )
    with Connection() as db:
        strategies = get_share_strategies(db, 1)
    for strategy in strategies:
        result = await strategy1(str(strategy.ticker))
        orders: list[Order] = []
        with Connection() as db:
            for r in result:
                order = db.query(Order).filter(Order.order_id == r.order_id).first()
                if order is None:
                    raise ValueError(f"Order {r.order_id} not found")
                orders.append(order)
        if not orders:
            continue
        message = f"Стратегия 1 для {strategy.ticker}:\n"
        limit_orders = [o for o in orders if str(o.type) == "ORDER_TYPE_LIMIT"]
        market_orders = [o for o in orders if str(o.type) == "ORDER_TYPE_MARKET"]
        limit_buys = [o for o in limit_orders if str(o.direction) == "BUY"]
        limit_sells = [o for o in limit_orders if str(o.direction) == "SELL"]
        market_buys = [o for o in market_orders if str(o.direction) == "BUY"]
        market_sells = [o for o in market_orders if str(o.direction) == "SELL"]

        if market_buys:
            message += f"Покупка по рынку: {len(market_buys)}\n"
        if market_sells:
            message += f"Продажа по рынку: {len(market_sells)}\n"
        if limit_buys:
            message += f"\nЛимитные заявки на покупку:\n"
            for order in limit_buys:
                price = order.price_units + order.price_nanos / 1_000_000_000

                message += f"Цена: {price} ({order.lots} лотов)\n"
        if limit_sells:
            message += f"\nЛимитные заявки на продажу:\n"
            for order in limit_sells:
                price = order.price_units + order.price_nanos / 1_000_000_000
                message += f"Цена: {price} ({order.lots} лотов)\n"
        await send_message(message)


def get_zone(price: Quotation, price_step: float, i: int):
    free_coef = 0.1
    zone_size = price * price_step
    if i > 0:
        zone_down = price + zone_size * (i - 1) - zone_size * free_coef + zone_size / 2
        zone_up = price + zone_size * i + zone_size * free_coef + zone_size / 2
    elif i < 0:
        i = -i
        zone_down = price - zone_size * i - zone_size * free_coef - zone_size / 2
        zone_up = price - zone_size * (i - 1) + zone_size * free_coef - zone_size / 2
    else:
        return price, price
    return zone_down, zone_up


async def strategy1(ticker: str) -> list[PostOrderResponse]:
    logger.info(f"Processing strategy 1 for {ticker}")
    with Connection() as db_session:
        strategy = get_share_strategies(db_session, 1, ticker)[0]
        transaction = Transaction(get_client())
        async with transaction:
            share = await transaction.client.get_share_by_ticker(ticker)
            if share is None:
                raise ValueError(f"Share {ticker} not found")

            if bool(strategy.need_reset):
                logger.info(f"Resetting strategy 1 for {ticker}")
                await transaction.client.cancel_all_orders(ticker=ticker)
                strategy.need_reset = False  # type: ignore
                db_session.commit()
                logger.info(f"Reset strategy 1 for {ticker}")

            if not bool(strategy.warmed_up):
                await strategy1_warmup(transaction, strategy)
                strategy.warmed_up = True  # type: ignore
                db_session.commit()
                logger.info(f"Warmed up strategy 1 for {ticker}")
                # strategy.warmed_up = True  # type: ignore
                # db_session.commit()
            await transaction.client.update_orders(
                on_cancel=on_update,
                on_reject=on_update,
            )

            last_price = await transaction.client.get_last_price(ticker=ticker)
            last_closed = await transaction.client.get_last_closed(ticker=ticker)
            if last_closed is not None:
                order = await transaction.client.get_order_info(
                    str(last_closed.order_id)
                )
                logger.debug(f"Last closed order: {order}")
                avg_price = order.average_position_price
                last_price = Quotation(avg_price.units, avg_price.nano)
                logger.debug(f"Using last closed price: {last_price}")
            else:
                logger.debug(f"Last price: {last_price}")

            free_capital = float(strategy.free_capital)  # type: ignore
            logger.debug(f"Free capital: {free_capital}")
            zone_id = -1
            current_price = await transaction.client.get_last_price(ticker=ticker)
            while free_capital > 0:
                zone_down, zone_up = get_zone(last_price, float(strategy.step_trigger) / 100, zone_id)  # type: ignore
                logger.debug(f"Zone {zone_id}: {zone_down} - {zone_up}")
                zone_down = Quotation(zone_down)
                zone_up = Quotation(zone_up)
                orders = await transaction.client.find_open_orders(
                    ticker=ticker, from_=zone_down, to=zone_up
                )
                zone_id -= 1
                if orders:
                    logger.debug(f"Filled with orders: {len(orders)}")
                    continue
                new_price = Quotation(zone_down + zone_up) / 2
                if new_price < Quotation(current_price) * 0.8:
                    logger.info(f"Price is less than 80%: {new_price}")
                    break
                if new_price > Quotation(current_price) * 1.2:
                    logger.info(f"Price is more than 120%: {new_price}")
                    break
                amount = new_price * int(strategy.step_amount)  # type: ignore
                if amount.amount > free_capital:  # type: ignore
                    break
                logger.debug(f"Zone is empty, buying")
                free_capital -= amount.amount
                await transaction.limit_buy(
                    ticker=ticker, lots=int(strategy.step_amount), price=new_price  # type: ignore
                )

            free_shares = await transaction.client.get_lots_amount(ticker=ticker)
            logger.debug(f"Free shares: {free_shares}")
            zone_id = 1
            while free_shares >= int(strategy.step_amount):  # type: ignore
                zone_down, zone_up = get_zone(
                    last_price, float(strategy.step_trigger) / 100, zone_id  # type: ignore
                )
                zone_id += 1
                logger.debug(f"Zone {zone_id}: {zone_down} - {zone_up}")
                zone_down = Quotation(zone_down)
                zone_up = Quotation(zone_up)
                orders = await transaction.client.find_open_orders(
                    ticker=ticker, from_=zone_down, to=zone_up
                )
                if orders:
                    logger.debug(f"Filled")
                    continue
                logger.debug(f"Zone is empty, selling")
                new_price = Quotation(zone_down + zone_up) / 2
                if new_price < Quotation(current_price) * 0.8:
                    logger.info(f"Price is less than 80%: {new_price}")
                    break
                if new_price > Quotation(current_price) * 1.2:
                    logger.info(f"Price is more than 120%: {new_price}")
                    break

                await transaction.limit_sell(
                    ticker=ticker, lots=int(strategy.step_amount), price=new_price  # type: ignore
                )
                free_shares -= int(strategy.step_amount)  # type: ignore

            logger.debug(f"Free shares: {free_shares}")
            logger.debug(f"Free capital: {free_capital}")
            strategy.free_capital = free_capital  # type: ignore
            db_session.commit()
        if transaction.is_successful:
            return transaction.get_orders()
        else:
            return []


async def strategy1_warmup(transaction: Transaction, strategy: ShareStrategy):
    ticker = str(strategy.ticker)
    logger.info(f"Warming up strategy 1 for {ticker}")
    logger.info(f"Current balance: {await transaction.client.get_balance()}")
    logger.info(f"Max capital: {strategy.max_capital}")

    if (await transaction.client.get_balance()).amount < float(strategy.max_capital):  # type: ignore
        raise ValueError(
            f"Not enough balance: {await transaction.client.get_balance()} < {strategy.max_capital}"
        )

    current_amount = await transaction.client.get_lots_amount(ticker=ticker)
    last_price = await transaction.client.get_last_price(ticker=ticker)
    logger.debug(f"Current amount: {current_amount}")
    logger.debug(f"Last price: {last_price}")
    share = await transaction.client.get_share_by_ticker(ticker)
    if share is None:
        raise ValueError(f"Share {ticker} not found")

    amount_to_buy = int(strategy.max_capital / 2 / last_price.amount)  # type: ignore
    if amount_to_buy == 0:
        raise ValueError(f"Not enough capital to buy {ticker}")
    amount_to_buy -= current_amount
    if amount_to_buy < 0:
        amount_to_buy = 0
    logger.info(f"Amount to buy: {amount_to_buy}")
    amount_to_buy -= amount_to_buy % share.lot
    if amount_to_buy > 0:
        await transaction.market_buy(ticker=ticker, lots=amount_to_buy)
    free_capital = strategy.max_capital - last_price.amount * (
        current_amount + amount_to_buy
    )
    if float(free_capital) < 0:  # type: ignore
        free_capital = 0
    strategy.free_capital = free_capital  # type: ignore
    logger.debug(f"Free capital: {free_capital}")
    logger.debug(f"Current balance: {await transaction.client.get_balance()}")
    logger.debug(
        f"Current amount: {await transaction.client.get_lots_amount(ticker=ticker)}"
    )
    logger.info(f"Warmed up strategy 1 for {ticker}")
