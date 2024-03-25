import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import base, ShareStrategy, Order


def get_session():
    from config import Config

    config = Config()  # type: ignore
    engine = create_engine(str(config.pg_dns))
    base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()
