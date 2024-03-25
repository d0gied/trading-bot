from re import S

from loguru import logger
from .models import Order, AddOrder, UpdateOrder
from sqlalchemy.orm import Session


def get_orders(
    session: Session,
    order_id: str | None = None,
    figi: str | None = None,
    # ticker: str | None = None,
    status: str | None = None,
    strategy_id: int | None = None,
) -> list[Order]:
    filt = []
    if order_id is not None:
        filt.append(Order.order_id == order_id)
    if figi is not None:
        filt.append(Order.figi == figi)
    # if ticker is not None:
    # filt.append(Order.ticker == ticker)
    if status is not None:
        filt.append(Order.status == status)
    if strategy_id is not None:
        filt.append(Order.strategy.strategy == strategy_id)
    if len(filt) == 0:
        return session.query(Order).all()
    return session.query(Order).filter(*filt).all()


def add_order(session: Session, order: AddOrder):
    if get_orders(session, order.order_id):
        logger.error(f"Order with order_id {order.order_id} already exists")
        raise ValueError(f"Order with order_id {order.order_id} already exists")
    session.add(Order(**order.model_dump()))
    session.commit()
    logger.debug(f"Added order with order_id {order.order_id}")


def update_order(session: Session, order: UpdateOrder):
    orders = get_orders(session, order.order_id)
    if orders:
        _order = orders[0]
        _order.status = order.status  # type: ignore
        logger.debug(
            f"Updated order with order_id {order.order_id}: status={order.status}"
        )
        session.commit()
    else:
        logger.error(f"Order with order_id {order.order_id} not found")
        raise ValueError(f"Order with order_id {order.order_id} not found")
