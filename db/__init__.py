import datetime
from enum import auto
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from .models import base, ShareStrategy, Order

from config import Config

config = Config()  # type: ignore
engine = create_engine(str(config.pg_dns))


def get_session():
    return sessionmaker(bind=engine)()
