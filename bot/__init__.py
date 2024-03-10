from aiogram import Bot, Dispatcher, types
from aiogram.fsm.storage.redis import RedisStorage
from .handlers.start import router as start_router
from .handlers.add import router as new_router
from .handlers.update import router as update_router
from .handlers.info import router as info_router
from .handlers.delete import router as del_router
from config import Config


def prepare(dp: Dispatcher) -> Dispatcher:
    dp.include_router(start_router)
    dp.include_router(new_router)
    dp.include_router(update_router)
    dp.include_router(info_router)
    dp.include_router(del_router)
    return dp
