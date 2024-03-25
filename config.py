from pydantic_settings import BaseSettings
from pydantic import Field, RedisDsn, PostgresDsn
from typing import Set


class Config(BaseSettings):
    BOT_TOKEN: str = Field(validation_alias="BOT_TOKEN")
    TINKOFF_TOKEN: str = Field(validation_alias="TINKOFF_TOKEN")
    MOEX_WORKING_HOURS: range = range(10, 24)

    ADMIN_IDS: Set[int] = Field(validation_alias="ADMIN_IDS")
    ADMIN_USERNAMES: Set[str] = Field(validation_alias="ADMIN_USERNAMES")

    redis_dns: RedisDsn = Field(validation_alias="REDIS_URL")
    pg_dns: PostgresDsn = Field(validation_alias="DATABASE_URL")
