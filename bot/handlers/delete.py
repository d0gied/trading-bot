from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from db import get_session
from db.strategies import del_share_strategy, get_share_strategies

from config import Config

from ..filters import IsPrivate, Admin

router = Router(name=__name__)
config = Config()  # type: ignore


@router.message(Command("delete"), IsPrivate(), Admin())
async def update_srategy(message: Message, state: FSMContext):
    keyboard = InlineKeyboardBuilder()
    keyboard.add(
        types.InlineKeyboardButton(
            text="Стратегия 1", callback_data="delete:strategy:1"
        ),
        types.InlineKeyboardButton(text="Отмена", callback_data="cancel"),
    )
    keyboard.adjust(1, repeat=True)

    ans = await message.answer(
        "Выберите стратегию, которую хотите обновить:",
        reply_markup=keyboard.as_markup(),  # type: ignore
    )
    await state.update_data(last_message_id=ans.message_id)
    await state.set_state("delete:strategy")


@router.callback_query(F.data.startswith("delete:strategy:"))
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
                text=_strategy.ticker, callback_data=f"delete:ticker:{_strategy.ticker}"
            )
        )
    keyboard.row(types.InlineKeyboardButton(text="Отмена", callback_data="cancel"))

    msg = await call.message.answer(
        "Выберите тикер, который хотите удалить:", reply_markup=keyboard.as_markup()
    )

    await state.update_data(last_message_id=msg.message_id)
    await state.update_data(strategy=strategy)
    await state.set_state("delete:ticker")


@router.callback_query(F.data.startswith("delete:ticker:"))
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

    msg = f"Тикер: {ticker}\n"
    msg += f"Стратегия: {strategy}\n"
    msg += f"Максимальный бюджет: {share_strategy[0].max_capital}\n"
    msg += f"Триггер: {share_strategy[0].step_trigger}%\n"
    msg += f"Количество акций: {share_strategy[0].step_amount}\n"
    msg += f"Удалить?"
    keyboard = InlineKeyboardBuilder()
    keyboard.add(types.InlineKeyboardButton(text="Да", callback_data="delete:confirm"))
    keyboard.add(types.InlineKeyboardButton(text="Нет", callback_data="cancel"))
    ans = await call.message.answer(msg, reply_markup=keyboard.as_markup())
    await state.update_data(last_message_id=ans.message_id)
    await state.update_data(share=ticker)
    await state.set_state("delete:confirm")


@router.callback_query(F.data == "delete:confirm")
async def confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    share = data["share"]
    strategy = data["strategy"]
    with get_session() as session:
        del_share_strategy(session, strategy, share)
    last_message_id = (await state.get_data()).get("last_message_id")
    if last_message_id:
        await call.message.bot.edit_message_reply_markup(
            call.message.chat.id, last_message_id, reply_markup=None
        )
    await call.message.answer("Стратегия удалена")
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
