import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from tinkoff.invest import AsyncClient

from bot import prepare
from config import Config
from trading import market_review, get_positions

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
strategies_data = {}


async def main() -> None:
    print("Starting bot...")
    bot = Bot(
        token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    botname = (await bot.me()).username
    bot_url = f"https://t.me/{botname}"
    print(f"Bot url: {bot_url}")
    async with AsyncClient(config.TINKOFF_TOKEN) as client:
        positions = await get_positions(client)
        for position in positions:
            print(position.figi, position.balance)
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        market_review,
        "cron",
        day_of_week="mon-fri",
        hour="10-23",
        minute="*",
        args=[bot, strategies_data],
    )
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
