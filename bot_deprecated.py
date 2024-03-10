"""All tgbot logic is here"""

import typing

import aiogram
from aiogram.contrib.fsm_storage.memory import MemoryStorage

from db.storage import UserStorage, User
from config import Config


class TG_Bot:
    def __init__(self, user_storage: UserStorage):
        self._user_storage: UserStorage = user_storage
        self._bot: aiogram.Bot = aiogram.Bot(token=Config.TGBOT_API_KEY)
        self._storage: MemoryStorage = MemoryStorage()
        self._dispatcher: aiogram.Dispatcher = aiogram.Dispatcher(
            self._bot, storage=self._storage
        )

    async def init(self):
        """Custom telegram bot initial function"""
        self._init_handler()

    async def start(self):
        """Aiogram bot startup"""
        print("Bot has started")
        await self._dispatcher.start_polling()

    async def send_signal(self, message: str):
        for user in await self._user_storage.get_all_members():
            try:
                await self._bot.send_message(user.user_id, message, parse_mode="HTML")
            except Exception:
                pass

    async def _show_menu(self, message: aiogram.types.Message, user: User):
        await message.answer("Добро пожаловать")

    def _init_handler(self):
        self._dispatcher.register_message_handler(
            self._user_middleware(self._show_menu), commands=["start", "menu"]
        )

    def _user_middleware(self, func: typing.Callable) -> typing.Callable:
        async def wrapper(message: aiogram.types.Message, *args, **kwargs):
            user = await self._user_storage.get_by_id(message.chat.id)
            if user is None:
                split_message = message.text.split()
                if len(split_message) == 2 and split_message[1] == Config.BOT_PASSWORD:
                    user = User(user_id=message.chat.id, role=User.USER)
                    await self._user_storage.create(user)
                    await func(message, user)
            elif user.role == User.BLOCKED:
                pass
            else:
                await func(message, user)

        return wrapper

    def _admin_required(self, func: typing.Callable) -> typing.Callable:
        async def wrapper(message: aiogram.types.Message, user: User, *args, **kwargs):
            if user.role == User.ADMIN:
                await func(message, user)

        return wrapper
