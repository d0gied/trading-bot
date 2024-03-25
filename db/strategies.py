from loguru import logger
from .models import ShareStrategy
from sqlalchemy.orm import Session


def get_share_strategies(
    session: Session, strategy: int | None = None, ticker: str | None = None
):
    if strategy is not None and ticker is not None:
        return (
            session.query(ShareStrategy)
            .filter(ShareStrategy.strategy == strategy)
            .filter(ShareStrategy.ticker == ticker)
            .all()
        )
    elif strategy is not None:
        return (
            session.query(ShareStrategy)
            .filter(ShareStrategy.strategy == strategy)
            .all()
        )
    elif ticker is not None:
        return session.query(ShareStrategy).filter(ShareStrategy.ticker == ticker).all()
    else:
        return session.query(ShareStrategy).all()


def add_share_strategy(
    session: Session,
    strategy: int,
    ticker: str,
    max_capital: float,
    step_trigger: float,
    step_amount: int,
    warmed_up: bool = False,
    need_reset: bool = True,
):
    session.add(
        ShareStrategy(
            strategy=strategy,
            ticker=ticker,
            max_capital=max_capital,
            step_trigger=step_trigger,
            step_amount=step_amount,
            warmed_up=warmed_up,
            need_reset=need_reset,
        )
    )
    logger.debug(f"Added share strategy {strategy} for {ticker}")
    session.commit()


def update_share_strategy(
    session: Session,
    strategy: int,
    ticker: str,
    max_capital: float | None = None,
    step_trigger: float | None = None,
    step_amount: int | None = None,
    warmed_up: bool | None = None,
    need_reset: bool = False,
):
    share_strategies = get_share_strategies(session, strategy, ticker)
    if share_strategies:
        share_strategy = share_strategies[0]
        if max_capital is not None:
            share_strategy.max_capital = max_capital  # type: ignore
        if step_trigger is not None:
            share_strategy.step_trigger = step_trigger  # type: ignore
        if step_amount is not None:
            share_strategy.step_amount = step_amount  # type: ignore
        if warmed_up is not None:
            share_strategy.warmed_up = warmed_up  # type: ignore
        if need_reset is not None:
            share_strategy.need_reset = need_reset  # type: ignore
        session.commit()


def del_share_strategy(session, strategy: int, ticker: str):
    share_strategies = get_share_strategies(session, strategy, ticker)
    if share_strategies:
        share_strategy = share_strategies[0]
        session.delete(share_strategy)
        session.commit()
    else:
        raise ValueError("Share strategy not found")
