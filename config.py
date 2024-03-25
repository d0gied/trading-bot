from pydantic_settings import BaseSettings
from pydantic import Field, RedisDsn, PostgresDsn


class Config(BaseSettings):
    BOT_TOKEN: str = Field(validation_alias="BOT_TOKEN")
    TINKOFF_TOKEN: str = Field(validation_alias="TINKOFF_TOKEN")
    MOEX_WORKING_HOURS: range = range(10, 24)

    ADMIN_IDS: list[int] = [299355675, 631874013, 1051336311]
    ADMIN_USERNAMES: list[str] = ["d0gied", "kokorev_artem", "fedexpress13"]

    redis_dns: RedisDsn = Field(validation_alias="REDIS_URL")
    pg_dns: PostgresDsn = Field(validation_alias="DATABASE_URL")
