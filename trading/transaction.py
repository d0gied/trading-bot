from loguru import logger
from .client import InvestClient
from .orders import Direction, LimitOrder, MarketOrder, Order, Quotation
from tinkoff.invest import PostOrderResponse


class Transaction:
    def __init__(self, client: InvestClient):
        self.client = client
        self.buffer: list[PostOrderResponse] = []
        self.is_successful = False

    async def __aenter__(self):
        self.client = await self.client.__aenter__()
        return self

    async def order(self, order: Order) -> PostOrderResponse:
        self.buffer.append(await self.client.order(order))
        logger.debug(f"Added order to transaction buffer: {order}")
        return self.buffer[-1]

    async def cancel(self):
        logger.info("Cancelling transaction orders")
        for order in self.buffer:
            await self.client.cancel_order(order.order_id)

    async def commit(self):
        logger.debug("Committing transaction orders")
        self.buffer.clear()

    async def limit(
        self,
        *,
        ticker: str,
        lots: int,
        price: Quotation | int | float,
        direction: Direction | str,
    ) -> None:
        await self.order(LimitOrder(ticker, lots, direction, price))

    async def market(
        self,
        *,
        ticker: str,
        lots: int,
        direction: Direction | str,
    ) -> None:
        await self.order(MarketOrder(ticker, lots, direction))

    async def limit_buy(
        self,
        *,
        ticker: str,
        lots: int,
        price: Quotation | int | float,
    ) -> None:
        await self.limit(ticker=ticker, lots=lots, price=price, direction=Direction.BUY)

    async def limit_sell(
        self,
        *,
        ticker: str,
        lots: int,
        price: Quotation | int | float,
    ) -> None:
        await self.limit(
            ticker=ticker, lots=lots, price=price, direction=Direction.SELL
        )

    async def market_buy(
        self,
        *,
        ticker: str,
        lots: int,
    ) -> None:
        await self.market(ticker=ticker, lots=lots, direction=Direction.BUY)

    async def market_sell(
        self,
        *,
        ticker: str,
        lots: int,
    ) -> None:
        await self.market(ticker=ticker, lots=lots, direction=Direction.SELL)

    async def __aexit__(self, exc_type, exc, tb):
        if exc:  # if an exception occurred
            error_path = f"{tb.tb_frame.f_code.co_filename}:{tb.tb_lineno}"
            logger.error(f"{error_path}: {exc}")
            try:
                await self.cancel()
            except Exception as e:
                logger.error(f"Error cancelling orders: {e}")
            self.is_successful = False
        else:
            self.is_successful = True
        await self.client.__aexit__(exc_type, exc, tb)

        return True  # suppress exceptions

    def get_orders(self) -> list[PostOrderResponse]:
        return self.buffer
