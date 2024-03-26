import datetime
from enum import auto
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import base, ShareStrategy, Order

from config import Config

config = Config()  # type: ignore


class Connection:
    def __init__(self):
        engine = create_engine(str(config.pg_dns))
        self.maker = sessionmaker(bind=engine)

    def __enter__(self) -> Session:
        self.session = self.maker()
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.session.close()
