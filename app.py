import json
import sys
from typing import Dict
import asyncio

from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage, Redis
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from loguru import logger
from tinkoff.invest import AsyncClient
from trading.client import get_client
from trading.strategies import tick

from bot import prepare
from config import Config

config = Config()  # type: ignore

redis_storage = RedisStorage(
    Redis(
        host=config.redis_dns.host,  # type: ignore
        port=config.redis_dns.port,  # type: ignore
        password=config.redis_dns.password,
    )
)

dp = Dispatcher(storage=redis_storage)
dp = prepare(dp)

logger.remove()  # remove default logger
logger.add(sys.stdout, level="INFO", format="{level} | {message}", colorize=True)
# logger.add("logs/bot.log", level="DEBUG", format="{time} | {level} | {message}")


async def main() -> None:
    logger.info("Starting bot...")
    bot = Bot(
        token=config.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    botname = (await bot.me()).username
    bot_url = f"https://t.me/{botname}"
    logger.info(f"Bot url: {bot_url}")
    for admin in config.ADMIN_IDS:
        logger.info(f"Admin id: {admin}")
    async with get_client() as client:
        logger.info(f"Client balance: {await client.get_balance()}")
        for pos in await client.get_positions():
            logger.info(f"Position: {pos}")

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        tick,
        "cron",
        day_of_week="mon-fri",
        hour="10-23",
        minute="*",
        timezone="Europe/Moscow",
    )
    scheduler.start()

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
