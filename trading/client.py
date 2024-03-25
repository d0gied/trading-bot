import datetime
from typing import Callable, Coroutine

from db.models import AddOrder, UpdateOrder
from .orders import Order, Direction, LimitOrder, MarketOrder, Quotation
from tinkoff.invest import (
    AsyncClient,
    Share,
    AccessLevel,
    AccountType,
    AccountStatus,
    OrderType,
    PostOrderResponse,
    OrderExecutionReportStatus as ExecutionStatus,
    AioRequestError,
    PositionsSecurities,
    PositionsResponse,
    Operation,
    OrderState,
)
from tinkoff.invest.async_services import AsyncServices
from config import Config
from loguru import logger
from aiocache import cached, Cache  # type: ignore
from .errors import InvestError
from sqlalchemy.orm import Session

from db.orders import add_order, update_order, Order as DBOrder
from db import get_session

config = Config()  # type: ignore


class InvestClient:
    def __init__(self, token: str) -> None:
        self.client = AsyncClient(token)
        self._client: AsyncServices
        self.is_opened = False

        self.buffer = []

    async def __aenter__(self) -> "InvestClient":
        self._client = await self.client.__aenter__()
        self.is_opened = True
        await self.health_check()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.client.__aexit__(exc_type, exc_val, exc_tb)
        self.is_opened = False
        if isinstance(exc_val, AioRequestError):
            error = InvestError(exc_val.args[1])
            logger.error(f"Error: {error}")

    @staticmethod
    def check_opened(f):
        async def wrapper(self, *args, **kwargs):
            if not self.is_opened:
                raise ValueError("Client is not opened")
            return await f(self, *args, **kwargs)

        return wrapper

    @check_opened
    async def health_check(self):
        accounts = (await self._client.users.get_accounts()).accounts
        if not accounts:
            logger.error("ACCOUNT: No accounts found")
            raise ValueError("No accounts found")
        elif len(accounts) > 1:
            logger.warning("ACCOUNT: More than one account found")

        account = accounts[0]
        if account.access_level != AccessLevel.ACCOUNT_ACCESS_LEVEL_FULL_ACCESS:
            logger.error("ACCESS: Account does not have full access")
            raise ValueError("Account does not have full access")

        if account.status != AccountStatus.ACCOUNT_STATUS_OPEN:
            logger.error("AVAILABLE: Account is not open")
            raise ValueError("Account is not open")

        logger.debug("Health check passed")

    @check_opened
    @cached(ttl=60, cache=Cache.MEMORY)
    async def get_account(self):
        response = await self._client.users.get_accounts()
        if not response.accounts:
            raise ValueError("No accounts found")
        return response.accounts[0]

    @check_opened
    async def log_info(self):
        account = await self.get_account()
        access = {
            AccessLevel.ACCOUNT_ACCESS_LEVEL_UNSPECIFIED: "Unspecified",
            AccessLevel.ACCOUNT_ACCESS_LEVEL_FULL_ACCESS: "Full access",
            AccessLevel.ACCOUNT_ACCESS_LEVEL_READ_ONLY: "Read only",
            AccessLevel.ACCOUNT_ACCESS_LEVEL_NO_ACCESS: "No access",
        }[account.access_level]
        type = {
            AccountType.ACCOUNT_TYPE_UNSPECIFIED: "Unspecified",
            AccountType.ACCOUNT_TYPE_TINKOFF: "Tinkoff",
            AccountType.ACCOUNT_TYPE_TINKOFF_IIS: "Tinkoff IIS",
            AccountType.ACCOUNT_TYPE_INVEST_BOX: "Invest box",
        }[account.type]
        status = {
            AccountStatus.ACCOUNT_STATUS_UNSPECIFIED: "Unspecified",
            AccountStatus.ACCOUNT_STATUS_NEW: "New",
            AccountStatus.ACCOUNT_STATUS_OPEN: "Open",
            AccountStatus.ACCOUNT_STATUS_CLOSED: "Closed",
        }[account.status]

        message = ""
        message += f"Name: {account.name}\n"
        message += f"Id: {account.id}\n"
        message += f"Type: {type}\n"
        message += f"Access level: {access}\n"
        message += f"Opened date: {account.opened_date:%d.%m.%Y}\n"
        message += f"Status: {status}"

        for msg in message.split("\n"):
            logger.info(msg)

    @check_opened
    @cached(ttl=60, cache=Cache.MEMORY)
    async def get_shares(self) -> list[Share]:
        shares = (await self._client.instruments.shares()).instruments
        shares = [
            share
            for share in shares
            if share.exchange
            in [
                "MOEX",
                "MOEX_EVENING_WEEKEND",
            ]  # filter only MOEX and MOEX_EVENING_WEEKEND shares# filter only MOEX and MOEX_EVENING_WEEKEND shares
        ]
        return shares

    @check_opened
    async def get_share_by_ticker(self, ticker: str) -> Share | None:
        shares = await self.get_shares()
        for share in shares:
            if share.ticker == ticker:
                return share
        return None

    @check_opened
    async def get_share_by_figi(self, figi: str) -> Share | None:
        shares = await self.get_shares()
        for share in shares:
            if share.figi == figi:
                return share
        return None

    @check_opened
    async def get_last_price(self, ticker: str) -> Quotation:
        share = await self.get_share_by_ticker(ticker)
        if share is None:
            raise ValueError(f"Share {ticker} not found")
        return Quotation(
            (await self._client.market_data.get_last_prices(figi=[share.figi]))
            .last_prices[0]
            .price
        )

    @check_opened
    async def get_last_closed(self, ticker: str):
        share = await self.get_share_by_ticker(ticker)
        if share is None:
            raise ValueError(f"Share {ticker} not found")
        db = get_session()
        today = datetime.datetime.now(datetime.timezone.utc)
        today = today.replace(hour=1, minute=0, second=0, microsecond=0)
        last = (
            db.query(DBOrder)
            .filter(
                (DBOrder.figi == share.figi)
                & (DBOrder.status == "fill")
                & (DBOrder.type == "limit")
                & (DBOrder.created_at > today)  # too old
            )
            .order_by(DBOrder.updated_at.desc())
            .first()
        )
        db.close()
        return last

    @check_opened
    async def get_order_info(self, order_id: str) -> OrderState:
        return await self._client.orders.get_order_state(
            account_id=(await self.get_account()).id,
            order_id=order_id,
        )

    @check_opened
    async def find_open_orders(self, ticker: str, from_: Quotation, to: Quotation):
        share = await self.get_share_by_ticker(ticker)
        if share is None:
            raise ValueError(f"Share {ticker} not found")
        db = get_session()
        orders = (
            db.query(DBOrder)
            .filter(
                (DBOrder.figi == share.figi)
                & (DBOrder.status == "created")
                & (
                    DBOrder.price_units * 10**9 + DBOrder.price_nanos
                    >= from_.units * 10**9 + from_.nano
                )
                & (
                    DBOrder.price_units * 10**9 + DBOrder.price_nanos
                    <= to.units * 10**9 + to.nano
                )
            )
            .all()
        )
        db.close()
        return orders

    @check_opened
    async def is_limit_available(self, ticker: str) -> bool:
        share = await self.get_share_by_ticker(ticker)
        if share is None:
            raise ValueError(f"Share {ticker} not found")
        response = await self._client.market_data.get_trading_status(figi=share.figi)
        return response.limit_order_available_flag

    @check_opened
    async def is_market_available(self, ticker: str) -> bool:
        share = await self.get_share_by_ticker(ticker)
        if share is None:
            raise ValueError(f"Share {ticker} not found")
        response = await self._client.market_data.get_trading_status(figi=share.figi)
        return response.market_order_available_flag

    @check_opened
    async def order(self, order: Order) -> PostOrderResponse:
        if not isinstance(order, Order):
            raise ValueError("Invalid order")
        logger.info(f"Creating order: {order}")
        share = await self.get_share_by_ticker(order.ticker)
        if not share:
            logger.error(f"Share {order.ticker} not found")
            raise ValueError(f"Share {order.ticker} not found")
        if order.lots <= 0:
            logger.error(f"Invalid lots: {order.lots}")
            raise ValueError(f"Invalid lots: {order.lots}")
        if order.lots % share.lot != 0:
            logger.error(f"Invalid lots: {order.lots} not a multiple of {share.lot}")
            raise ValueError(
                f"Invalid lots: {order.lots} not a multiple of {share.lot}"
            )

        order_id = str(datetime.datetime.now(datetime.timezone.utc).timestamp())
        order_type: OrderType = OrderType.ORDER_TYPE_UNSPECIFIED
        price: Quotation = Quotation(0)
        if isinstance(order, LimitOrder):
            order_type = OrderType.ORDER_TYPE_LIMIT
            price = order.price
            min_increment = share.min_price_increment
            bn_price = price.units * 10**9 + price.nano
            bn_min_increment = min_increment.units * 10**9 + min_increment.nano
            bn_price = round(bn_price / bn_min_increment) * bn_min_increment
            price = Quotation(bn_price // 10**9, bn_price % 10**9)
            if not (await self.is_limit_available(order.ticker)):
                logger.error(f"Limit orders are not available for {order.ticker}")
                raise ValueError(f"Limit orders are not available for {order.ticker}")
        elif isinstance(order, MarketOrder):
            order_type = OrderType.ORDER_TYPE_MARKET
            if not (await self.is_market_available(order.ticker)):
                logger.error(f"Market orders are not available for {order.ticker}")
                raise ValueError(f"Market orders are not available for {order.ticker}")
        if order_type == OrderType.ORDER_TYPE_UNSPECIFIED:
            logger.error("Invalid order: {order}")
            raise ValueError("Invalid order")

        order_response = await self._client.orders.post_order(
            instrument_id=share.figi,
            figi=share.figi,
            order_type=order_type,
            quantity=order.lots // share.lot,
            price=price,
            direction=order.direction.to_order_direction(),
            order_id=str(order_id),
            account_id=(await self.get_account()).id,
        )
        logger.debug(
            f"Created order: figi={share.figi},"
            f"order_id={order_id}, order_type={order_type},"
            f"quantity={order.lots}, price={price},"
            f"direction={order.direction.to_order_direction()},"
            f"account_id={(await self.get_account()).id}"
        )
        logger.info(f"Order {order_response.order_id} created")
        add_order(
            get_session(),
            AddOrder(
                order_id=order_response.order_id,
                figi=share.figi,
                lots=order.lots,
                price_units=price.units,
                price_nanos=price.nano,
                direction=order.direction.name,
                type=order_type.name,
                status="created",
                account_id=(await self.get_account()).id,
            ),
        )
        return order_response

    @check_opened
    async def limit(
        self,
        *,
        ticker: str,
        lots: int,
        price: Quotation | int | float,
        direction: Direction,
    ) -> None:
        if isinstance(price, (int, float)):
            price = Quotation(price)
        await self.order(LimitOrder(ticker, lots, direction, price))

    @check_opened
    async def market(
        self,
        *,
        ticker: str,
        lots: int,
        direction: Direction,
    ) -> None:
        await self.order(MarketOrder(ticker, lots, direction))

    @check_opened
    async def limit_buy(
        self,
        *,
        ticker: str,
        lots: int,
        price: Quotation | int | float,
    ) -> None:
        if isinstance(price, (int, float)):
            price = Quotation(price)
        await self.limit(ticker=ticker, lots=lots, price=price, direction=Direction.BUY)

    @check_opened
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

    @check_opened
    async def market_buy(
        self,
        *,
        ticker: str,
        lots: int,
    ) -> None:
        await self.market(ticker=ticker, lots=lots, direction=Direction.BUY)

    @check_opened
    async def market_sell(
        self,
        *,
        ticker: str,
        lots: int,
    ) -> None:
        await self.market(ticker=ticker, lots=lots, direction=Direction.SELL)

    @check_opened
    async def cancel_order(self, order_id: str):
        db = get_session()
        order = db.query(DBOrder).filter_by(order_id=order_id).first()
        if not order:
            logger.error(f"Order {order_id} not found")
            raise ValueError(f"Order {order_id} not found")

        await self._client.orders.cancel_order(
            account_id=(await self.get_account()).id,
            order_id=order_id,
        )
        logger.info(f"Order {order_id} canceled")

    @check_opened
    async def get_positions(
        self,
        *,
        ticker: str | None = None,
        figi: str | None = None,
    ) -> list[PositionsSecurities]:
        if ticker and figi:
            raise ValueError("Both ticker and figi are specified")

        account_id = (await self.get_account()).id
        positions: PositionsResponse = await self._client.operations.get_positions(
            account_id=account_id
        )
        if ticker:
            share = await self.get_share_by_ticker(ticker)
            if not share:
                raise ValueError(f"Share {ticker} not found")
            figi = share.figi

        return [
            position
            for position in positions.securities
            if (not figi) or (position.figi == figi)
        ]

    @check_opened
    async def get_lots(self, figi: str) -> int:
        positions = await self.get_positions()
        for position in positions:
            if position.figi == figi:
                return position.balance
        return 0

    @check_opened
    async def get_balance(self, currency: str = "rub") -> Quotation:
        account_id = (await self.get_account()).id
        response = await self._client.operations.get_positions(account_id=account_id)
        money = response.money
        for position in money:
            if position.currency == currency:
                return Quotation(position.units, position.nano)
        raise ValueError(f"Currency {currency} not found")

    async def get_history(
        self, ticker: str, from_: datetime.datetime, to: datetime.datetime
    ) -> list[Operation]:
        share = await self.get_share_by_ticker(ticker)
        if not share:
            raise ValueError(f"Share {ticker} not found")
        return (
            await self._client.operations.get_operations(
                from_=from_,
                to=to,
                figi=share.figi,
                account_id=(await self.get_account()).id,
            )
        ).operations

    @check_opened
    async def process_order(
        self,
        order_response: OrderState,
        db_order: DBOrder,
        session: Session,
        on_fill: Callable[[str], Coroutine] | None = None,
        on_reject: Callable[[str], Coroutine] | None = None,
        on_cancel: Callable[[str], Coroutine] | None = None,
    ):
        status = "unknown"
        match order_response.execution_report_status:
            case ExecutionStatus.EXECUTION_REPORT_STATUS_NEW:
                status = "created"
            case ExecutionStatus.EXECUTION_REPORT_STATUS_FILL:
                status = "fill"
            case ExecutionStatus.EXECUTION_REPORT_STATUS_REJECTED:
                status = "rejected"
            case ExecutionStatus.EXECUTION_REPORT_STATUS_CANCELLED:
                status = "cancelled"
            case ExecutionStatus.EXECUTION_REPORT_STATUS_PARTIALLYFILL:
                status = "created"
            case _:
                status = "unknown"  # type: ignore
        if str(status) != str(db_order.status):
            update_order(session, UpdateOrder(order_id=db_order.order_id, status=status))  # type: ignore
            logger.info(
                f"Order {db_order.order_id} updated: {db_order.status} -> {status}"
            )
            if status == "fill" and on_fill is not None:
                await on_fill(order_response.order_id)
            if status == "rejected" and on_reject is not None:
                await on_reject(order_response.order_id)
            if status == "cancelled" and on_cancel is not None:
                await on_cancel(order_response.order_id)
        else:
            logger.debug(f"Order {db_order.order_id} unchanged: {status}")

    @check_opened
    async def update_orders(
        self,
        on_fill: Callable[[str], Coroutine] | None = None,
        on_reject: Callable[[str], Coroutine] | None = None,
        on_cancel: Callable[[str], Coroutine] | None = None,
    ):
        session = get_session()
        db_orders = (
            session.query(DBOrder)
            .filter((DBOrder.status == "created") | (DBOrder.status == "unknown"))
            .all()
        )

        active_orders = (
            await self._client.orders.get_orders(
                account_id=(await self.get_account()).id
            )
        ).orders
        active_orders_ids = [active_order.order_id for active_order in active_orders]

        if not db_orders:
            logger.info("No orders to update")
        else:
            logger.info(f"Updating {len(db_orders)} orders")

        for db_order in db_orders:
            if db_order.order_id not in active_orders_ids:
                order_response = await self._client.orders.get_order_state(
                    account_id=db_order.account_id, order_id=db_order.order_id  # type: ignore
                )
                await self.process_order(
                    order_response,
                    db_order,
                    session,
                    on_fill,
                    on_reject,
                    on_cancel,
                )

        session.commit()
        session.close()

    @check_opened
    async def get_lots_amount(
        self, *, ticker: str | None = None, figi: str | None = None
    ) -> int:
        positions = await self.get_positions(ticker=ticker, figi=figi)
        return sum([position.balance for position in positions])

    @check_opened
    async def cancel_all_orders(
        self, *, ticker: str | None = None, figi: str | None = None
    ):
        if not ticker and not figi:
            raise ValueError("Both ticker and figi are not specified")
        if ticker:
            logger.info(f"Cancelling all orders for {ticker}")
            share = await self.get_share_by_ticker(ticker)
            if not share:
                raise ValueError(f"Share {ticker} not found")
            figi = share.figi
        else:
            logger.info(f"Cancelling all orders for {figi}")

        orders = await self._client.orders.get_orders(
            account_id=(await self.get_account()).id
        )
        for order in orders.orders:
            if order.figi == figi:
                await self.cancel_order(order.order_id)
                logger.info(f"Order {order.order_id} canceled")


def get_client(token: str = config.TINKOFF_TOKEN):
    return InvestClient(token)
