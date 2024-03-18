from pydantic_settings import BaseSettings
from pydantic import Field, RedisDsn, PostgresDsn


class Config(BaseSettings):
    BOT_TOKEN: str = Field(validation_alias="BOT_TOKEN")
    TINKOFF_TOKEN: str = Field(validation_alias="TINKOFF_TOKEN")
    SANDBOX_TOKEN: str = Field(validation_alias="SANDBOX_TOKEN")
    MOEX_WORKING_HOURS: range = range(10, 24)

    ADMIN_IDS: list[int] = []
    ADMIN_USERNAMES: list[str] = ["d0gied", "kokorev_artem", "fedexpress13"]

    redis_dns: RedisDsn = Field(validation_alias="REDIS_URL")
    pg_dns: PostgresDsn = Field(validation_alias="DATABASE_URL")

    class Config:
        ...
        # env_file = ".env"
        # env_file_encoding = "utf-8"


# class Config:
#     TINKOFF_TOKEN = "t.nb6zNANS5GyESI_e_9ledD8iWDqVpgEK9ewrQu6Orr6F9N-NNdklR5r9VkwFs8RXiPzkXgxeUtcGSf_LxFgXAw"

#     MOEX_WORKING_HOURS = range(10, 24)

#     HOST = "some_ip"
#     PORT = "5432"
#     LOGIN = "some_login"
#     PASSWORD = "some_password"
#     DATABASE = "tradingbot"

#     BOT_PASSWORD = "aboba"

#     # Настройки, которые нужно будет перенести куда-то где их можно менять
#     tickers = ["SBER"]
#     share_max_budget = 10000
#     trigger_delta = 0.5
#     share_lot_size = 1
