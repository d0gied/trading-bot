from requests import get

URL = "https://raw.githubusercontent.com/RussianInvestments/investAPI/main/src/docs/errors/api_errors.json"
DATA = get(URL).json()


class InvestError(Exception):
    def __init__(self, code: int):
        self.code = code
        self.message = DATA[code]["message"]
        self.description = DATA[code]["description"]
        self.type = DATA[code]["type"]

    def __str__(self):
        return f"[{self.code}] {self.description}"

    def __repr__(self):
        return f"InvestError({self.code})"
