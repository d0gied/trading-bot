from aiogram import F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.filters import callback_data
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InputMediaPhoto, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import get_session
from db.strategies import get_share_strategies, update_share_strategy
from Levenshtein import distance

from config import Config
from trading import InvestClient

from ..filters import IsPrivate, Admin

router = Router(name=__name__)
config = Config()  # type: ignore


@router.message(Command("update"), IsPrivate(), Admin())
async def update_srategy(message: Message, state: FSMContext):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(
            text="Стратегия 1", callback_data="update:strategy:1"
        ),
        types.InlineKeyboardButton(text="Отмена", callback_data="cancel"),
    )
    keyboard.adjust(1, repeat=True)

    ans = await message.answer(
        "Выберите стратегию, которую хотите обновить:",
        reply_markup=keyboard.as_markup(),  # type: ignore
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("update:strategy")


@router.callback_query(F.data.startswith("update:strategy:"))
async def update_strategy(call: CallbackQuery, state: FSMContext):
    strategy = int(call.data.split(":")[2])
    strategies = get_share_strategies(get_session(), strategy=strategy)
    if not strategies:
        await call.message.answer("Эта стратегия еще не используется")
        return

    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.message.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )

    keyboard = InlineKeyboardBuilder()
    for _strategy in strategies:
        keyboard.add(
            types.InlineKeyboardButton(
                text=_strategy.ticker, callback_data=f"update:ticker:{_strategy.ticker}"
            )
        )
    keyboard.row(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))

    msg = await call.message.answer(
        "Выберите тикер, который хотите обновить:", reply_markup=keyboard.as_markup()
    )

    await state.update_data(last_message_id=msg.message_id)
    print(strategy)
    await state.update_data(strategy=strategy)
    await state.set_state("update:ticker")


@router.callback_query(F.data.startswith("update:ticker:"))
async def update_ticker(call: CallbackQuery, state: FSMContext):
    ticker = call.data.split(":")[2]
    strategy = (await state.get_data()).get("strategy")
    print(strategy, ticker)
    share_strategy = get_share_strategies(get_session(), strategy, ticker)
    if not share_strategy:
        await call.message.answer("Этот тикер не используется в этой стратегии")
        return

    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.message.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    await call.message.answer("Выбран актив: " + ticker)
    msg = await call.message.answer(
        f"Введите максимальный бюджет(в валюте актива):",
        reply_markup=keyboard.as_markup(),
    )
    await state.update_data(share=ticker)
    await state.update_data(last_message_id=msg.message_id)
    await state.set_state("update:capital")


@router.message(StateFilter("update:capital"))
async def capital(message: Message, state: FSMContext):
    try:
        capital = float(message.text)
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
    await state.set_state("update:trigger")


@router.message(StateFilter("update:trigger"))
async def trigger(message: Message, state: FSMContext):
    text = message.text
    if text.endswith("%"):
        text = text[:-1]
    try:
        trigger = float(text)
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
        "Введите количество акций для покупки/продажи при срабатывании триггера:",
        reply_markup=keyboard.as_markup(),
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("update:amount")


@router.message(StateFilter("update:amount"))
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
    msg += f"Количество акций: {amount}\n"
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(text="Продолжить", callback_data="continue")
    )
    keyboard.add(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))
    ans = await message.answer(msg, reply_markup=keyboard.as_markup())
    await state.update_data(last_message_id=ans.message_id)
    await state.update_data(amount=amount)
    await state.set_state("update:confirm")


@router.callback_query(F.data == "continue", StateFilter("update:confirm"))
async def confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    share = data["share"]
    strategy = data["strategy"]
    capital = data["capital"]
    trigger = data["trigger"]
    amount = data["amount"]
    with get_session() as session:
        update_share_strategy(session, strategy, share, capital, trigger, amount)
    await call.message.answer("Обновлено")
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
