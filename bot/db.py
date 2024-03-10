from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy import Column, Integer, String, Float, DateTime
from config import Config

config = Config()
base = declarative_base()


class ShareStrategy(base):
    __tablename__ = "share_strategy"
    strategy = Column(Integer, primary_key=True)
    ticker = Column(String, primary_key=True)
    max_capital = Column(Float)
    step_trigger = Column(Float)
    step_amount = Column(Integer)


engine = create_engine(str(config.pg_dns))
base.metadata.create_all(engine)


def get_session():
    return sessionmaker(bind=engine)()


def get_share_strategies(session, strategy: int = None, ticker: str = None):
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
    session,
    strategy: int,
    ticker: str,
    max_capital: float,
    step_trigger: float,
    step_amount: int,
):
    session.add(
        ShareStrategy(
            strategy=strategy,
            ticker=ticker,
            max_capital=max_capital,
            step_trigger=step_trigger,
            step_amount=step_amount,
        )
    )
    session.commit()


def update_share_strategy(
    session,
    strategy: int,
    ticker: str,
    max_capital: float,
    step_trigger: float,
    step_amount: int,
):
    share_strategies = get_share_strategies(session, strategy, ticker)
    print(share_strategies)
    if share_strategies:
        share_strategy = share_strategies[0]
        share_strategy.max_capital = max_capital
        share_strategy.step_trigger = step_trigger
        share_strategy.step_amount = step_amount
        session.commit()
    else:
        add_share_strategy(
            session, strategy, ticker, max_capital, step_trigger, step_amount
        )


def del_share_strategy(session, strategy: int, ticker: str):
    share_strategies = get_share_strategies(session, strategy, ticker)
    if share_strategies:
        share_strategy = share_strategies[0]
        session.delete(share_strategy)
        session.commit()
    else:
        raise ValueError("Share strategy not found")
