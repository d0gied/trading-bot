class Config:
    TINKOFF_TOKEN = "t.nb6zNANS5GyESI_e_9ledD8iWDqVpgEK9ewrQu6Orr6F9N-NNdklR5r9VkwFs8RXiPzkXgxeUtcGSf_LxFgXAw"

    MOEX_WORKING_HOURS = range(10, 24)

    HOST = "some_ip"
    PORT = "5432"
    LOGIN = "some_login"
    PASSWORD = "some_password"
    DATABASE = "tradingbot"

    BOT_PASSWORD = "aboba"

    # Настройки, которые нужно будет перенести куда-то где их можно менять
    tickers = ["SBER"]
    share_max_budget = 10000
    trigger_delta = 0.5
    share_lot_size = 1
