from aiogram import Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from ..filters import IsPrivate, Admin


router = Router(name=__name__)


@router.message(Command("start"), IsPrivate(), Admin())
async def start(message: Message, state: FSMContext):
    await message.answer("Привет, администратор!")
    await message.answer(
        """Я бот для управления стратегиями инвестирования.
Вы можете добавить, удалить, обновить или посмотреть информацию о стратегиях.
/add - добавить стратегию
/delete - удалить стратегию
/update - обновить стратегию
/info - посмотреть информацию о стратегиях"""
    )
