from requests import get
from tinkoff.invest import AioRequestError

URL = "https://raw.githubusercontent.com/RussianInvestments/investAPI/main/src/docs/errors/api_errors.json"
DATA = get(URL).json()


class InvestError(Exception):
    def __new__(cls, base: Exception):
        if isinstance(base, AioRequestError) and base.code in DATA:
            return super().__new__(cls)
        return base

    def __init__(self, base: AioRequestError):
        self.code = base.code
        self.message = DATA[self.code]["message"]
        self.description = DATA[self.code]["description"]
        self.type = DATA[self.code]["type"]

    def __str__(self):
        return f"[{self.code}] {self.description}"

    def __repr__(self):
        return f"InvestError({self.code})"
