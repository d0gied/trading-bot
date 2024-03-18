import datetime
from decimal import Decimal
from typing import Optional, List, Dict

import aiogram
from tinkoff.invest.sandbox.client import SandboxClient
from tinkoff.invest.services import InstrumentsService
from tinkoff.invest.utils import decimal_to_quotation, quotation_to_decimal
from tinkoff.invest import (
    AsyncClient,
    OrderType,
    OrderState,
    OrderDirection,
    PostOrderResponse,
    Quotation,
    GetOrdersResponse,
    MoneyValue,
)
from tinkoff.invest.async_services import AsyncServices
from tradingview_ta import TA_Handler, Interval

from tinkoff.invest.sandbox.client import SandboxClient

from config import Config
from bot.db import (
    ShareStrategy,
    add_share_strategy,
    get_session,
    get_share_strategies,
    update_share_strategy,
)


def float_to_quotation(value):
    units = int(value)
    nano = int((value - units + 1e-10) * 1_000_000_000)
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


async def order(
    figi: str,
    price: float,
    quantity: int,
    direction: int,
    client: AsyncClient,
    order_type: int = OrderType.ORDER_TYPE_LIMIT,
) -> PostOrderResponse:
    account_id = await get_account_id(client)
    made_order: PostOrderResponse = await client.orders.post_order(
        instrument_id=figi,
        account_id=account_id,
        price=float_to_quotation(price),
        quantity=quantity,
        direction=direction,
        order_type=order_type,
        order_id=str(datetime.datetime.utcnow().timestamp()),
    )
    if made_order.execution_report_status != 1:
        print(figi, made_order)
    return made_order


def get_analysis(symbol: str):
    try:
        data = TA_Handler(
            symbol=symbol,
            screener="russia",
            exchange="MOEX",
            interval=Interval.INTERVAL_1_MINUTE,
        )
        analysis = data.get_analysis()
        return analysis
    except Exception:
        return None


def analize_strategy(
    strategy: ShareStrategy, share: dict, purchases: dict, client: SandboxClient
) -> List[str]:
    analysis = get_analysis(strategy.ticker)
    candle_close: float = analysis.indicators["close"]
    messages_to_send = []
    if strategy.ticker not in purchases.keys():
        # purchases[strategy.ticker]["last_price"] = candle_close
        purchases[strategy.ticker]["available"] = strategy.max_capital
        lots_quantity = int(
            strategy.max_capital // (candle_close * strategy.step_amount * share["lot"])
        )
        market_buy_order = await order(
            share["figi"],
            candle_close,
            lots_quantity * share["lot"],
            OrderDirection.ORDER_DIRECTION_BUY,
            client,
            OrderType.ORDER_TYPE_MARKET,
        )
        purchases[strategy.ticker]["available"] -= moneyvalue_to_float(
            market_buy_order.total_order_amount
        )
        buy_price = moneyvalue_to_float(market_buy_order.executed_order_price)
        lots_quantity = market_buy_order.lots_executed
        if lots_quantity == 0:
            message = f"ОШИБКА\n\n{strategy.ticker} не купилась ни разу, проверьте настройки стратегии"
            return messages_to_send
        message = f"ПОДГОТОВКА по {strategy.ticker}\n\n"
        for i in range(1, lots_quantity + 1):
            purchases[strategy.ticker]["min_price"] = buy_price
            sell_price = round(
                candle_close * (1 + (strategy.step_trigger / 100) * i), 9
            )
            sell_order = await order(
                share["figi"],
                sell_price,
                strategy.step_amount,
                OrderDirection.ORDER_DIRECTION_SELL,
                client,
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
                purchases[strategy.ticker]["sells"].pop(sell_id)
                if purchases[strategy.ticker]["buys"]:
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
                    buy_order = await order(
                        share["figi"],
                        new_buy_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_BUY,
                        client,
                    )
                    purchases[strategy.ticker]["buys"].append(buy_order.order_id)
                    purchases[strategy.ticker]["available"] = (
                        strategy.max_capital
                        - new_buy_price * strategy.step_amount * share["lot"]
                    )
                    purchases[strategy.ticker]["min_price"] = new_buy_price
                    message = f"СДЕЛКА\n\n{strategy.ticker} продана по цене {moneyvalue_to_float(selled_order.average_position_price)}, выставлена к покупке по цене {new_buy_price} и отменена к продаже по цене {purchases[strategy.ticker]['max_price']}"
                else:
                    message = f"СДЕЛКА\n\n{strategy.ticker} куплена по цене {moneyvalue_to_float(selled_order.average_position_price)}, новая сделка не выставлена, т.к. нет средств"
                messages_to_send.append(message)
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
                    buy_order = await order(
                        share["figi"],
                        new_buy_price,
                        strategy.step_amount,
                        OrderDirection.ORDER_DIRECTION_BUY,
                        client,
                    )
                    purchases[strategy.ticker]["buys"].append(buy_order.order_id)
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
    sandbox_client: SandboxClient,
    sandbox_account_id: str,
    tg_bot: aiogram.Bot,
    purchases: Dict[str, Dict],
):
    config = Config()
    strategies = get_share_strategies(get_session())
    messages_to_send = []
    async with AsyncClient(config.TINKOFF_TOKEN) as async_client:
        shares = await get_shares(
            async_client, [strategy.ticker for strategy in strategies]
        )
        strategies_as_shares = {share["ticker"]: share for share in shares}
        for strategy in strategies:
            messages = analize_strategy(
                strategy,
                strategies_as_shares[strategy.ticker],
                purchases,
                sandbox_client,
            )
            messages_to_send.extend(messages)
        # await send_messages(messages_to_send, tg_bot, config.ADMIN_USERNAMES)

    # strategies_tickers = [strategy.ticker for strategy in strategies]
    # async with AsyncClient(config.TINKOFF_TOKEN) as client:
    #     shares = await get_shares(client, strategies_tickers)
    #     for share in shares:
    #         trade = await analize_share(share, purchases)
    # if trade is not None:
    #     await send_message(tg_bot, trade)
