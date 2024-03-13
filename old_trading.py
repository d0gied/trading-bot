import datetime
from typing import Optional, List, Dict

import aiogram
from tinkoff.invest.sandbox.client import SandboxClient
from tinkoff.invest.services import InstrumentsService
from tinkoff.invest.utils import quotation_to_decimal
from tinkoff.invest import (
    AsyncClient,
    OrderType,
    OrderState,
    OrderDirection,
    PostOrderResponse,
    Quotation,
    GetOrdersResponse,
)
from tinkoff.invest.async_services import AsyncServices
from tradingview_ta import TA_Handler, Interval

from config import Config
from bot.db import (
    ShareStrategy,
    add_share_strategy,
    get_session,
    get_share_strategies,
    update_share_strategy,
)


def float_to_quotation(value):
    value = round(value, 9)
    units = int(value)
    nano = int((value - units) * 1_000_000_000)
    return Quotation(units=units, nano=nano)


async def get_account_id(token: str):
    async with AsyncClient(token) as client:
        accounts = await client.users.get_accounts()
        return accounts.accounts[0].id


def moneyvalue_to_float(moneyvalue):
    return moneyvalue.units + moneyvalue.nano / 1_000_000_000


async def get_shares(client: AsyncServices, tickers: List[str] = None) -> List[Dict]:
    """Get shares from Tinkoff API by tickers or all of them"""
    instruments: InstrumentsService = client.instruments
    shares = []
    for method in ["shares"]:
        for item in (await getattr(instruments, method)()).instruments:
            if item.exchange in ["MOEX", "MOEX_EVENING_WEEKEND"] and (
                tickers is None or item.ticker in tickers
            ):
                shares.append(
                    {
                        "name": item.name,
                        "ticker": item.ticker,
                        "class_code": item.class_code,
                        "figi": item.figi,
                        "uid": item.uid,
                        "type": method,
                        "min_price_increment": float(
                            quotation_to_decimal(item.min_price_increment)
                        ),
                        "scale": 9 - len(str(item.min_price_increment.nano)) + 1,
                        "lot": item.lot,
                        "api_trade_available_flag": item.api_trade_available_flag,
                        "currency": item.currency,
                        "exchange": item.exchange,
                        "buy_available_flag": item.buy_available_flag,
                        "sell_available_flag": item.sell_available_flag,
                        "short_enabled_flag": item.short_enabled_flag,
                        "klong": float(quotation_to_decimal(item.klong)),
                        "kshort": float(quotation_to_decimal(item.kshort)),
                    }
                )
    return shares


async def limit_order(
    figi: str,
    price: float,
    quantity: int,
    direction: int,
    client: AsyncClient,
) -> PostOrderResponse:
    account_id = await get_account_id(client)
    order: PostOrderResponse = await client.orders.post_order(
        instrument_id=figi,
        account_id=account_id,
        price=float_to_quotation(price),
        quantity=quantity,
        direction=direction,
        order_type=OrderType.ORDER_TYPE_LIMIT,
        order_id=str(datetime.datetime.utcnow().timestamp()),
    )
    if order.execution_report_status != 1:
        print(figi, order)
    return order


async def analize_strategy(
    strategy: ShareStrategy, purchases: dict, config: Config, tg_bot: aiogram.Bot
) -> Optional[Dict]:
    try:
        data = TA_Handler(
            symbol=strategy.ticker,
            screener="russia",
            exchange="MOEX",
            interval=Interval.INTERVAL_1_MINUTE,
        )
        analysis = data.get_analysis()
        candle_close: float = analysis.indicators["close"]
        with SandboxClient(config.TINKOFF_TOKEN) as client:
            share = (await get_shares(client, [strategy.ticker]))[0]
            if strategy.ticker not in purchases.keys():
                purchases[strategy.ticker]["last_price"] = candle_close
                purchases[strategy.ticker]["available"] = strategy.max_capital
                depth = 0
                while purchases[strategy.ticker]["available"] > (
                    candle_close
                    * (1 - (strategy.step_trigger / 100) * depth)
                    * strategy.step_amount
                    * share["lot"]
                ):
                    buy_price = round(
                        candle_close * (1 - (strategy.step_trigger / 100) * depth), 9
                    )
                    buy_order = await limit_order(
                        share["figi"],
                        buy_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_BUY,
                        client,
                    )
                    purchases[strategy.ticker]["buys"].append(buy_order.order_id)
                    purchases[strategy.ticker]["available"] -= (
                        buy_price * strategy.step_amount * share["lot"]
                    )
                    purchases[strategy.ticker]["min_price"] = buy_price
                    message = f"СДЕЛКА\n\n{strategy.ticker} {'выставлена к покупке' if depth else 'куплена'} по цене {buy_price} и выставлена к продаже по цене {round(candle_close * (1 + (strategy.step_trigger / 100) * (depth+1)),9)}"
                    depth += 1
                    sell_price = round(
                        candle_close * (1 + (strategy.step_trigger / 100) * depth), 9
                    )
                    sell_order = await limit_order(
                        share["figi"],
                        sell_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_SELL,
                        client,
                    )
                    purchases[strategy.ticker]["sells"].append(sell_order.order_id)
                    purchases[strategy.ticker]["max_price"] = sell_price
                    await send_message(message, tg_bot, config)
                if depth == 0:
                    message = f"ОШИБКА\n\n{strategy.ticker} не купилась ни разу, проверьте настройки стратегии"
                    await send_message(message, tg_bot, config)
            else:
                active_orders: GetOrdersResponse = await client.orders.get_orders(
                    account_id=await get_account_id(client)
                )
                active_orders_ids = [order.order_id for order in active_orders.orders]
                buys_ids = purchases[strategy.ticker]["buys"]
                for buy_id in buys_ids:
                    if buy_id not in active_orders_ids:
                        bought_order: OrderState = await client.orders.get_order_state(
                            account_id=await get_account_id(client),
                            order_id=buy_id,
                        )
                        purchases[strategy.ticker]["buys"].pop(buy_id)
                        sell_id_to_cancel = purchases[strategy.ticker]["sells"][-1]
                        purchases[strategy.ticker]["sells"].pop(sell_id_to_cancel)
                        await client.orders.cancel_order(
                            account_id=await get_account_id(client),
                            order_id=sell_id_to_cancel,
                        )
                        new_buy_price = round(
                            purchases[strategy.ticker]["min_price"]
                            * (1 - (strategy.step_trigger / 100)),
                            9,
                        )
                        if purchases[strategy.ticker]["available"] > (
                            new_buy_price * strategy.step_amount * share["lot"]
                        ):
                            buy_order = await limit_order(
                                share["figi"],
                                new_buy_price,
                                strategy.step_amount,
                                OrderDirection.ORDER_DIRECTION_BUY,
                                client,
                            )
                            purchases[strategy.ticker]["buys"].append(
                                buy_order.order_id
                            )
                            purchases[strategy.ticker]["available"] -= (
                                new_buy_price * strategy.step_amount * share["lot"]
                            )
                            purchases[strategy.ticker]["min_price"] = new_buy_price
                            message = f"СДЕЛКА\n\n{strategy.ticker} куплена по цене {moneyvalue_to_float(bought_order.average_position_price)}, выставлена к покупке по цене {new_buy_price}, отменена к продаже по цене {purchases[strategy.ticker]['max_price']} и выставлена к продаже по цене "
                            purchases[strategy.ticker]["max_price"] = round(
                                purchases[strategy.ticker]["max_price"]
                                / (1 + (strategy.step_trigger / 100)),
                                9,
                            )
                        else:
                            message = f"СДЕЛКА\n\n{strategy.ticker} куплена по цене {moneyvalue_to_float(bought_order.average_position_price)}, отменена к продаже по цене {purchases[strategy.ticker]['max_price']}, новая сделка не выставлена, т.к. нет средств"
                        await send_message(message, tg_bot, config)
                sells_ids = purchases[strategy.ticker]["sells"]
                for sell_id in sells_ids:
                    if sell_id not in active_orders_ids:
                        selled_order: OrderState = await client.orders.get_order_state(
                            account_id=await get_account_id(client),
                            order_id=sell_id,
                        )
                        purchases[strategy.ticker]["sells"].pop(sell_id)
                        buy_id_to_cancel = purchases[strategy.ticker]["buys"][-1]
                        purchases[strategy.ticker]["buys"].pop(buy_id_to_cancel)
                        await client.orders.cancel_order(
                            account_id=await get_account_id(client),
                            order_id=buy_id_to_cancel,
                        )
                        purchases[strategy.ticker]["min_price"] = round(
                            purchases[strategy.ticker]["min_price"]
                            * (1 - (strategy.step_trigger / 100)),
                            9,
                        )
                        new_sell_price = round(
                            purchases[strategy.ticker]["max_price"]
                            * (1 + (strategy.step_trigger / 100)),
                            9,
                        )
                        if purchases[strategy.ticker]["available"] > (
                            new_buy_price * strategy.step_amount * share["lot"]
                        ):
                            buy_order = await limit_order(
                                share["figi"],
                                new_buy_price,
                                strategy.step_amount,
                                OrderDirection.ORDER_DIRECTION_BUY,
                                client,
                            )
                            purchases[strategy.ticker]["buys"].append(
                                buy_order.order_id
                            )
                            purchases[strategy.ticker]["available"] = (
                                strategy.max_capital
                                - new_buy_price * strategy.step_amount * share["lot"]
                            )
                            purchases[strategy.ticker]["min_price"] = new_buy_price
                            message = f"СДЕЛКА\n\n{strategy.ticker} продана по цене {moneyvalue_to_float(selled_order.average_position_price)}, выставлена к покупке по цене {new_buy_price} и отменена к продаже по цене {purchases[strategy.ticker]['max_price']}"
                        else:
                            message = f"СДЕЛКА\n\n{strategy.ticker} куплена по цене {moneyvalue_to_float(selled_order.average_position_price)}, новая сделка не выставлена, т.к. нет средств"
                        await send_message(message, tg_bot, config)
    except Exception:
        return None


async def send_message(message: str, tg_bot: aiogram.Bot, config: Config):
    for admin in config.ADMIN_USERNAMES:
        try:
            await tg_bot.send_message(admin, message)
        except Exception:
            pass


async def market_review(tg_bot: aiogram.Bot, purchases: Dict[str, Dict]):
    config = Config()
    strategies = get_share_strategies(get_session())
    for strategy in strategies:
        await analize_strategy(strategy, purchases, config, tg_bot)
    # strategies_tickers = [strategy.ticker for strategy in strategies]
    # async with AsyncClient(config.TINKOFF_TOKEN) as client:
    #     shares = await get_shares(client, strategies_tickers)
    #     for share in shares:
    #         trade = await analize_share(share, purchases)
    # if trade is not None:
    #     await send_message(tg_bot, trade)
