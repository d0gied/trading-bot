import asyncio
import datetime
from typing import List, Dict

import aiogram
from tinkoff.invest.services import InstrumentsService
from tinkoff.invest.utils import quotation_to_decimal, now
from tinkoff.invest import (
    CandleInterval,
    HistoricCandle,
    AsyncClient,
    OrderType,
    OrderState,
    OrderDirection,
    PostOrderResponse,
    Quotation,
    GetOrdersResponse,
    PositionsResponse,
    PositionsSecurities,
)
from tinkoff.invest.async_services import AsyncServices

from config import Config
from bot.db import (
    ShareStrategy,
    get_session,
    get_share_strategies,
)


def float_to_quotation(value):
    units = int(value)
    nano = int((value - units + 1e-10) * 1_000_000_000)
    return Quotation(units=units, nano=nano)


async def get_account_id(client: AsyncClient):
    accounts = await client.users.get_accounts()
    return accounts.accounts[0].id


def moneyvalue_to_float(moneyvalue):
    return moneyvalue.units + moneyvalue.nano / 1_000_000_000


async def get_last_candle(share: dict, client: AsyncClient) -> HistoricCandle:
    last_candle = None
    while last_candle is None:
        async for candle in client.get_all_candles(
            figi=share["figi"],
            from_=now() - datetime.timedelta(minutes=1),
            interval=CandleInterval.CANDLE_INTERVAL_1_MIN,
        ):
            last_candle = candle
        await asyncio.sleep(5)
    return last_candle


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


async def create_order(
    figi: str,
    price: float,
    quantity: int,
    direction: OrderDirection,
    order_type: OrderType,
    client: AsyncClient,
) -> PostOrderResponse:
    account_id = await get_account_id(client)
    order: PostOrderResponse = await client.orders.post_order(
        instrument_id=figi,
        account_id=account_id,
        price=price,
        quantity=quantity,
        direction=direction,
        order_type=order_type,
        order_id=str(datetime.datetime.now(datetime.UTC).timestamp()),
    )
    if order.execution_report_status not in (1, 4):
        print(figi, order)
    return order


async def get_positions(client: AsyncClient) -> List[PositionsSecurities]:
    account_id = await get_account_id(client)
    positions: PositionsResponse = await client.operations.get_positions(
        account_id=account_id
    )
    return positions.securities


async def analize_strategy(
    strategy: ShareStrategy,
    share: dict,
    purchases: dict,
    positions: Dict[str, PositionsSecurities],
    client: AsyncClient,
) -> List[str]:
    last_candle = await get_last_candle(share, client)
    candle_close: float = float(quotation_to_decimal(last_candle.close))
    messages_to_send = []
    if purchases.get(strategy.ticker) is None:
        purchases[strategy.ticker]["available"] = strategy.max_capital
        lots_quantity = int(
            strategy.max_capital // (candle_close * strategy.step_amount * share["lot"])
        )
        if lots_quantity == 0:
            messages_to_send.append(
                f"ПРЕДУПРЕЖДЕНИЕ\n\n{strategy.ticker} не выставилась на покупку, проверьте настройки стратегии"
            )
        message = f"ПОДГОТОВКА по {strategy.ticker}\n\n"
        for i in range(1, lots_quantity + 1):
            buy_price = candle_close * (1 - (strategy.step_trigger / 100) * i)
            buy_price -= buy_price % share["min_price_increment"]
            buy_order = await create_order(
                figi=share["figi"],
                price=buy_price,
                quantity=strategy.step_amount,
                direction=OrderDirection.ORDER_DIRECTION_BUY,
                order_type=OrderType.ORDER_TYPE_LIMIT,
                client=client,
            )
            message += f"Выставлена к покупке по цене {buy_price}\n"
            purchases[strategy.ticker]["available"] -= moneyvalue_to_float(
                buy_price * strategy.step_amount * share["lot"]
            )
            purchases[strategy.ticker]["buys"].append(buy_order.order_id)
            purchases[strategy.ticker]["min_price"] = buy_price
        lots_to_sell = positions[share["figi"]] // (
            candle_close * strategy.step_amount * share["lot"]
        )
        for i in range(1, lots_to_sell + 1):
            sell_price = candle_close * (1 + (strategy.step_trigger / 100) * i)
            sell_price -= sell_price % share["min_price_increment"]
            sell_order = await create_order(
                figi=share["figi"],
                price=sell_price,
                quantity=strategy.step_amount,
                direction=OrderDirection.ORDER_DIRECTION_SELL,
                order_type=OrderType.ORDER_TYPE_LIMIT,
                client=client,
            )
            purchases[strategy.ticker]["sells"].append(sell_order.order_id)
            purchases[strategy.ticker]["max_price"] = sell_price
            message += f"Выставлена к продаже по цене {sell_price}\n"
        messages_to_send.append(message)
    else:
        active_orders: GetOrdersResponse = await client.orders.get_orders(
            account_id=await get_account_id(client)
        )
        active_orders_ids = [order.order_id for order in active_orders.orders]
        sells_ids = purchases[strategy.ticker]["sells"]
        for sell_id in sells_ids:
            if sell_id not in active_orders_ids:
                selled_order: OrderState = await client.orders.get_order_state(
                    account_id=await get_account_id(client),
                    order_id=sell_id,
                )
                purchases[strategy.ticker]["available"] += moneyvalue_to_float(
                    selled_order.executed_order_price
                )
                purchases[strategy.ticker]["sells"].pop(sell_id)
                message = f"СДЕЛКА по {strategy.ticker}\n\nПродажа по цене {moneyvalue_to_float(selled_order.average_position_price)}"
                if purchases[strategy.ticker]["buys"]:
                    buy_id_to_cancel = purchases[strategy.ticker]["buys"][-1]
                    purchases[strategy.ticker]["buys"].pop(buy_id_to_cancel)
                    await client.orders.cancel_order(
                        account_id=await get_account_id(client),
                        order_id=buy_id_to_cancel,
                    )
                    message += f"Отменена к покупке по цене {purchases[strategy.ticker]['min_price']}"
                koef = 1 + (strategy.step_trigger / 100)
                new_buy_price = purchases[strategy.ticker]["min_price"] * koef
                new_sell_price = purchases[strategy.ticker]["max_price"] * koef
                new_sell_price -= new_sell_price % share["min_price_increment"]
                new_buy_price -= new_buy_price % share["min_price_increment"]
                sell_order = await create_order(
                    figi=share["figi"],
                    price=new_sell_price,
                    quantity=strategy.step_amount,
                    direction=OrderDirection.ORDER_DIRECTION_SELL,
                    order_type=OrderType.ORDER_TYPE_LIMIT,
                    client=client,
                )
                purchases[strategy.ticker]["sells"].append(sell_order.order_id)
                message += f"\nВыставлена к продаже по цене {new_sell_price}\n"
                if purchases[strategy.ticker]["available"] > (
                    new_buy_price * strategy.step_amount * share["lot"]
                ):
                    buy_order = await create_order(
                        share["figi"],
                        new_buy_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_BUY,
                        OrderType.ORDER_TYPE_LIMIT,
                        client,
                    )
                    purchases[strategy.ticker]["buys"].append(buy_order.order_id)
                    purchases[strategy.ticker]["available"] = (
                        strategy.max_capital
                        - new_buy_price * strategy.step_amount * share["lot"]
                    )
                    purchases[strategy.ticker]["min_price"] = new_buy_price
                    message += f"\nВыставлена к покупке по цене {new_buy_price}"
                purchases[strategy.ticker]["max_price"] = new_sell_price
                messages_to_send.append(message)
        buys_ids = purchases[strategy.ticker]["buys"]
        for buy_id in buys_ids:
            if buy_id not in active_orders_ids:
                bought_order: OrderState = await client.orders.get_order_state(
                    account_id=await get_account_id(client),
                    order_id=buy_id,
                )
                purchases[strategy.ticker]["buys"].pop(buy_id)
                message = f"СДЕЛКА по {strategy.ticker}\n\nПокупка по цене {moneyvalue_to_float(bought_order.average_position_price)}"
                if purchases[strategy.ticker]["sells"]:
                    sell_id_to_cancel = purchases[strategy.ticker]["sells"][-1]
                    purchases[strategy.ticker]["sell"].pop(sell_id_to_cancel)
                    await client.orders.cancel_order(
                        account_id=await get_account_id(client),
                        order_id=sell_id_to_cancel,
                    )
                    message += f"Отменена к продаже по цене {purchases[strategy.ticker]['min_price']}"
                koef = 1 - (strategy.step_trigger / 100)
                new_buy_price = purchases[strategy.ticker]["min_price"] * koef
                new_sell_price = purchases[strategy.ticker]["max_price"] * koef
                new_sell_price -= new_sell_price % share["min_price_increment"]
                new_buy_price -= new_buy_price % share["min_price_increment"]
                sell_order = await create_order(
                    figi=share["figi"],
                    price=new_sell_price,
                    quantity=strategy.step_amount,
                    direction=OrderDirection.ORDER_DIRECTION_SELL,
                    order_type=OrderType.ORDER_TYPE_LIMIT,
                    client=client,
                )
                purchases[strategy.ticker]["sells"].append(sell_order.order_id)
                message += f"\nВыставлена к продаже по цене {new_sell_price}\n"
                if purchases[strategy.ticker]["available"] > (
                    new_buy_price * strategy.step_amount * share["lot"]
                ):
                    buy_order = await create_order(
                        share["figi"],
                        new_buy_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_BUY,
                        OrderType.ORDER_TYPE_LIMIT,
                        client,
                    )
                    purchases[strategy.ticker]["buys"].append(buy_order.order_id)
                    purchases[strategy.ticker]["available"] = (
                        strategy.max_capital
                        - new_buy_price * strategy.step_amount * share["lot"]
                    )
                    purchases[strategy.ticker]["min_price"] = new_buy_price
                    message += f"\nВыставлена к покупке по цене {new_buy_price}"
                purchases[strategy.ticker]["max_price"] = new_sell_price
                messages_to_send.append(message)
    return messages_to_send


async def send_messages(
    messages: List[str], tg_bot: aiogram.Bot, admin_usernames: Config
):
    for admin in admin_usernames:
        for message in messages:
            try:
                await tg_bot.send_message(admin, message)
            except Exception:
                pass


async def market_review(
    tg_bot: aiogram.Bot,
    purchases: Dict[str, Dict],
):
    config = Config()
    strategies = get_share_strategies(get_session())
    messages_to_send = []
    async with AsyncClient(config.TINKOFF_TOKEN) as client:
        positions = await get_positions(client)
        positions_dict = {position.figi: position for position in positions}
        shares = await get_shares(client, [strategy.ticker for strategy in strategies])
        strategies_as_shares = {share["ticker"]: share for share in shares}
        for strategy in strategies:
            if purchases.get(strategy.ticker) is None:
                purchases[strategy.ticker] = {}
            messages = await analize_strategy(
                strategy,
                strategies_as_shares[strategy.ticker],
                purchases,
                positions_dict,
                client,
            )
            messages_to_send.extend(messages)
        await send_messages(messages_to_send, tg_bot, config.ADMIN_USERNAMES)
