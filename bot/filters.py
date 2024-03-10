import asyncio
from logging import config
from typing import Any

from aiogram.enums import ChatMemberStatus
from aiogram.filters import Filter, logic
from aiogram.types import CallbackQuery, Message

from config import Config

config = Config()


class Admin(Filter):
    async def __call__(self, message: Message) -> bool:
        user = message.from_user
        if user is None:
            return False
        return (user.id in config.ADMIN_IDS) or (  # type: ignore
            user.username in config.ADMIN_USERNAMES  # type: ignore
        )


class IsPrivate(Filter):
    async def __call__(self, message: Message | CallbackQuery) -> bool:
        if isinstance(message, Message):
            return message.chat.type == "private"
        elif isinstance(message, CallbackQuery):
            if not message.message:
                return False
            return message.message.chat.type == "private"
