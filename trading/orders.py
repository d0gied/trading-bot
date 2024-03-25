from dataclasses import dataclass
from enum import Enum
from math import e
from typing import Any, Union, overload
from tinkoff.invest import Quotation as TinkoffQuotation, OrderDirection


class Direction(Enum):
    UNKNOWN = 0
    BUY = 1
    SELL = 2

    @classmethod
    def from_str(cls, s: str) -> "Direction":
        if s.lower() == "buy":
            return cls.BUY
        elif s.lower() == "sell":
            return cls.SELL
        raise ValueError(f"Invalid direction: {s}", s)

    @classmethod
    def from_order_direction(cls, d: OrderDirection) -> "Direction":
        if d == OrderDirection.ORDER_DIRECTION_BUY:
            return cls.BUY
        elif d == OrderDirection.ORDER_DIRECTION_SELL:
            return cls.SELL
        raise ValueError(f"Invalid direction: {d}", d)

    def to_order_direction(self) -> OrderDirection:
        if self == self.BUY:
            return OrderDirection.ORDER_DIRECTION_BUY
        elif self == self.SELL:
            return OrderDirection.ORDER_DIRECTION_SELL
        raise ValueError(f"Invalid direction: {self}", self)


@dataclass
class Order:
    ticker: str
    lots: int
    direction: Direction

    def __init__(
        self,
        ticker: str,
        lots: int,
        direction: Union[Direction, str],
    ) -> None:
        self.ticker = ticker
        self.lots = lots
        self.direction = (
            Direction.from_str(direction) if isinstance(direction, str) else direction
        )


class LimitOrder(Order):
    price: "Quotation"

    def __init__(
        self,
        ticker: str,
        lots: int,
        direction: Union[Direction, str],
        price: Union["Quotation", int, float],
    ) -> None:
        super().__init__(ticker, lots, direction)
        if isinstance(price, (int, float)):
            price = Quotation(price)
        self.price = price

    def __str__(self) -> str:
        return (
            f"{self.direction.name} {self.lots} lots of {self.ticker} at {self.price}"
        )


class MarketOrder(Order):
    def __str__(self) -> str:
        return (
            f"{self.direction.name} {self.lots} lots of {self.ticker} at market price"
        )


class Quotation(TinkoffQuotation):
    @overload
    def __init__(self, units: int, nano: int) -> None: ...

    @overload
    def __init__(self, quotation: TinkoffQuotation) -> None: ...

    @overload
    def __init__(self, amount: float | int) -> None: ...

    def __init__(self, *args, **kwargs):
        units: int = -1
        nano: int = -1
        if kwargs:
            raise ValueError("Only positional arguments are allowed")
        if len(args) == 1 and isinstance(args[0], TinkoffQuotation):
            units = args[0].units
            nano = args[0].nano
        if len(args) == 2:
            units = args[0]  # type: ignore
            nano = args[1]  # type: ignore
        if len(args) == 1 and isinstance(args[0], (float, int)):
            f = args[0]
            units = int(f)
            nano = int((f - units) * 1_000_000_000)
        if units == -1 or nano == -1:
            raise ValueError("Invalid arguments")
        super().__init__(units, nano)

    def __str__(self) -> str:
        return f"{self.units}.{self.nano:09d}"

    def to_float(self) -> float:
        return self.units + self.nano / 1_000_000_000

    @property
    def amount(self) -> float:
        return self.to_float()

    def __float__(self) -> float:
        return self.to_float()

    def __int__(self) -> int:
        return self.units

    def __mul__(self, other: float) -> "Quotation":
        return Quotation(self.to_float() * other)

    def __truediv__(self, other: float) -> "Quotation":
        return Quotation(self.to_float() / other)
