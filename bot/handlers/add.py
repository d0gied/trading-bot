from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.filters import callback_data
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import get_session
from db.strategies import add_share_strategy, get_share_strategies

from Levenshtein import distance

from config import Config
from trading import InvestClient, get_client

from ..filters import IsPrivate, Admin

router = Router(name=__name__)
config = Config()  # type: ignore


@router.message(Command("add"), IsPrivate(), Admin())
async def new_srategy(message: Message, state: FSMContext):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="Список тикеров", callback_data="shares"),
        types.InlineKeyboardButton(text="Отмена", callback_data="cancel"),
    )
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await message.bot.edit_message_reply_markup(
            message.chat.id, last_message_id, reply_markup=None
        )

    ans = await message.answer(
        "Ввведите тикер актива, который хотите добавить в стратегии:",
        reply_markup=keyboard.as_markup(),  # type: ignore
    )
    await state.set_state("add:share")
    await state.update_data(last_message_id=ans.message_id)


@router.callback_query(F.data == "shares")
async def shares(call: CallbackQuery, state: FSMContext):
    async with get_client() as client:
        shares = await client.get_shares()
    msg = []
    for share in shares:
        msg.append(f"<code>{share.ticker}</code> - {share.name}. Lot: {share.lot}")
    cnt = len(msg)
    await call.message.answer("\n".join(msg[: cnt // 2]))
    await call.message.answer("\n".join(msg[cnt // 2 :]))
    if await state.get_state() == "add:share":
        last_message_id = (await state.get_data()).get("last_message_id")
        if last_message_id:
            await call.message.bot.edit_message_reply_markup(
                call.message.chat.id, last_message_id, reply_markup=None
            )

        keyboard = InlineKeyboardBuilder()
        keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
        ans = await call.message.answer(
            "Введите тикер актива, который хотите добавить в стратегии:",
            reply_markup=keyboard.as_markup(),
        )
        await state.update_data(last_message_id=ans.message_id)


@router.message(StateFilter("add:share"))
async def share(message: Message, state: FSMContext):
    share = message.text.upper()
    async with get_client() as client:
        shares = await client.get_shares()
    shares = [share.ticker for share in shares]
    shares.sort(key=lambda x: distance(x, share))
    share = shares[0]

    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="Стратегия 1", callback_data="strategy:1"),
        types.InlineKeyboardButton(text="Отмена", callback_data="cancel"),
    )
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await message.bot.edit_message_reply_markup(
            message.chat.id, last_message_id, reply_markup=None
        )

    ans = await message.answer(
        f"Выбран тикер: {share}", reply_markup=keyboard.as_markup()
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.update_data(share=share)
    await state.set_state("add:strategy")


@router.callback_query(F.data.startswith("strategy:"))
async def strategy(call: CallbackQuery, state: FSMContext):
    strategy = int(call.data.split(":")[1])
    with get_session() as session:
        share = (await state.get_data())["share"]
        if get_share_strategies(session, strategy, share):
            await call.message.answer(
                "Стратегия уже существует, используйте /update чтобы изменить ее или /delete чтобы удалить"
            )
            return
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )
    message = f"Выбрана стратегия: {strategy}\n\nВведите максимальный бюджет(в валюте актива):"

    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    ans = await call.message.answer(message, reply_markup=keyboard.as_markup())
    await state.update_data(strategy=strategy)
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("add:capital")


@router.message(StateFilter("add:capital"))
async def capital(message: Message, state: FSMContext):
    try:
        capital = float(message.text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число")
        return
    await state.update_data(capital=capital)
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await message.bot.edit_message_reply_markup(
            message.chat.id, last_message_id, reply_markup=None
        )
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    ans = await message.answer(
        "Введите изменение цены для срабатывания триггера(в процентах):",
        reply_markup=keyboard.as_markup(),
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("add:trigger")


@router.message(StateFilter("add:trigger"))
async def trigger(message: Message, state: FSMContext):
    text = message.text
    if text.endswith("%"):
        text = text[:-1]
    try:
        trigger = float(text.replace(",", "."))
    except ValueError:
        await message.answer("Введите число")
        return
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await message.bot.edit_message_reply_markup(
            message.chat.id, last_message_id, reply_markup=None
        )

    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    await state.update_data(trigger=trigger)
    ans = await message.answer(
        "Введите количество лотов для покупки/продажи при срабатывании триггера:",
        reply_markup=keyboard.as_markup(),
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("add:amount")


@router.message(StateFilter("add:amount"))
async def amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
    except ValueError:
        await message.answer("Введите число")
        return
    data = await state.get_data()
    share = data["share"]
    strategy = data["strategy"]
    capital = data["capital"]
    trigger = data["trigger"]
    msg = f"Стратегия для {share}:\n"
    msg += f"Максимальный бюджет: {capital}\n"
    msg += f"Триггер: {trigger}%\n"
    msg += f"Количество лотов: {amount}\n"
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="Продолжить", callback_data="continue")
    )
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    ans = await message.answer(msg, reply_markup=keyboard.as_markup())
    await state.update_data(last_message_id=ans.message_id)
    await state.update_data(amount=amount)
    await state.set_state("add:confirm")


@router.callback_query(F.data == "continue", StateFilter("add:confirm"))
async def confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    share = data["share"]
    strategy = data["strategy"]
    capital = data["capital"]
    trigger = data["trigger"]
    amount = data["amount"]
    with get_session() as session:
        add_share_strategy(
            session,
            strategy,
            share,
            capital,
            trigger,
            amount,
        )
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.message.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )
    await call.message.answer("Добавлено")
    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel(call: CallbackQuery, state: FSMContext):
    await call.message.answer("Отменено")
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.message.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )
    await state.clear()
