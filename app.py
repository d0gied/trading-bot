import asyncio
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, Redis
from bot import prepare
from config import Config

config = Config()

redis_storage = RedisStorage(
    Redis(
        host=config.redis_dns.host,  # type: ignore
        port=config.redis_dns.port,  # type: ignore
        password=config.redis_dns.password,
    )
)

dp = Dispatcher(storage=redis_storage)
dp = prepare(dp)


async def main() -> None:
    print("Starting bot...")
    bot = Bot(
        token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    botname = (await bot.me()).username
    bot_url = f"https://t.me/{botname}"
    print(f"Bot url: {bot_url}")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
