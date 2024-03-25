from venv import logger
from .client import InvestClient, get_client
from .transaction import Transaction
from db.strategies import get_share_strategies
from db.orders import Order, get_orders
from db import get_session


async def tick():
    async with get_client() as client:
        await client.update_orders()

    strategies = get_share_strategies(get_session(), 1)
    for strategy in strategies:
        await strategy1(str(strategy.ticker), 1)


async def on_update(order_id: str):
    order = get_orders(get_session(), order_id=order_id)[0]


async def strategy1(ticker: str, strategy: int):
    db_session = get_session()
    logger.info(f"Processing strategy 1 for {ticker}")

    async with Transaction(get_client()) as transaction:
        active_orders = get_orders(db_session, ticker=ticker, status="created")
