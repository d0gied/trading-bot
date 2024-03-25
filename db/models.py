import datetime
from typing import Literal
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel

from config import Config

config = Config()  # type: ignore
base = declarative_base()


class ShareStrategy(base):
    __tablename__ = "share_strategy"
    strategy = Column(Integer, primary_key=True)
    ticker = Column(String, primary_key=True)
    max_capital = Column(Float)
    step_trigger = Column(Float)
    step_amount = Column(Integer)


class Order(base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True)
    created_at = Column(
        DateTime,
        default=datetime.datetime.now,
    )
    updated_at = Column(
        DateTime,
        default=datetime.datetime.now,
        onupdate=datetime.datetime.now,
    )
    order_id = Column(String, nullable=False)  # order_id = orderId
    figi = Column(String, nullable=False)
    lots = Column(Integer, nullable=False)  # lots = quantity of shares
    price_units = Column(Integer)
    price_nanos = Column(Integer)  # price = price_units + price_nanos / 1e9
    direction = Column(String)  # buy or sell
    type = Column(String)  # limit or market
    status = Column(String)  # status of order
    account_id = Column(String)


class AddOrder(BaseModel):
    order_id: str
    figi: str
    lots: int
    price_units: int
    price_nanos: int
    direction: str
    type: str
    status: str
    account_id: str


class UpdateOrder(BaseModel):
    order_id: str
    status: str
