import datetime
from typing import Optional, List, Dict

from tinkoff.invest import AsyncClient
from tinkoff.invest.services import InstrumentsService
from tinkoff.invest.utils import quotation_to_decimal
from tinkoff.invest import (
    AsyncClient,
    OrderType,
    OrderDirection,
)
from tinkoff.invest.async_services import AsyncServices

from config import Config

config = Config()


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


async def trade_by_ticker(
    ticker: str,
    trade_direction: int,
    quantity: int,
    token: str,
):
    # trade_direction : buy - 1, sell - 2
    async with AsyncClient(token) as client:
        accounts = await client.users.get_accounts()
        instrument_figi = (await get_shares(client, [ticker]))[0]["figi"]
        order = await client.orders.post_order(
            figi=instrument_figi,
            account_id=accounts.accounts[0].id,
            quantity=quantity,
            direction=trade_direction,
            order_type=OrderType.ORDER_TYPE_MARKET,
            order_id=str(datetime.datetime.utcnow().timestamp()),
        )
        if order.execution_report_status != 1:
            print(ticker, order)
        return order


async def get_account_id(token: str):
    async with AsyncClient(token) as client:
        accounts = await client.users.get_accounts()
        return accounts.accounts[0].id


def moneyvalue_to_float(moneyvalue):
    return moneyvalue.units + moneyvalue.nano / 1_000_000_000


async def analize_share(share: dict, purchases: dict) -> Optional[Dict]:
    return None


# async def send_message(tg_bot: TG_Bot, trade: Dict):
#     if trade["type"] == 2:
#         message_text = f"ПРОДАЖА\n\nПокупка {trade['ticker']} {trade['date_buy']} по цене {trade['price_buy']} с коммисией {trade['buy_commission']}\nКол-во: {trade['quantity']}\n\nПродажа {trade['date_sell']} по цене {trade['price_sell']} с коммисией {trade['sell_commission']}\n\nПрибыль: {trade['profit']}"
#     else:
#         message_text = f"ПОКУПКА\n\nПокупка {trade['ticker']} {trade['date_buy']} по цене {trade['price_buy']} с коммисией {trade['buy_commission']}\nКол-во: {trade['quantity']}"
#     await tg_bot.send_signal(
#         message=message_text,
#     )


# async def market_review(tg_bot: TG_Bot, purchases: Dict[str, Dict]):
#     async with AsyncClient(config.TINKOFF_TOKEN) as client:
#         shares = await get_shares(client)
#     time_now = datetime.datetime.now()
#     if time_now.hour in config.MOEX_WORKING_HOURS:
#         for share in shares:
#             trade = await analize_share(share, purchases)
#             if trade is not None:
#                 await send_message(tg_bot, trade)
