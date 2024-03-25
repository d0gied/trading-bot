import asyncio
import datetime
import time

from loguru import logger
from trading.client import InvestClient, get_client
from trading.transaction import Transaction


async def main() -> None:
    transaction = Transaction(get_client())
    async with transaction:
        await transaction.client.update_orders()
        # await transaction.limit_buy(ticker="MVID", lots=1, price=199.2)
        time.sleep(5)
        a = 1 / 0


if __name__ == "__main__":
    asyncio.run(main())
