import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import base, ShareStrategy, Order
from config import Config

config = Config()  # type: ignore
engine = create_engine(str(config.pg_dns))
base.metadata.create_all(engine)


def get_session():
    return sessionmaker(bind=engine)()
