import logging
import asyncio
import re
import random
from collections import defaultdict, deque
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.filters import Command

def split_message(text, limit=4000):
    parts = []
    while len(text) > limit:
        cut = text.rfind("\n", 0, limit)
        if cut == -1:
            cut = limit
        parts.append(text[:cut])
        text = text[cut:]
    parts.append(text)
    return parts


OWNER_ID = "UR_ID"  # ← Вставь свое айди сюда

TOKEN = "UR_TOKEN"  # ← Вставь свой токен сюда

logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Хранилища
tickets = defaultdict(lambda: defaultdict(int))         # chat_id -> user_id -> билеты
timers = {}                                             # chat_id -> (end_time, task)
last_hits = defaultdict(lambda: defaultdict(lambda: deque(maxlen=3)))     # ⚽️ 🏀
cube_streaks = defaultdict(lambda: defaultdict(lambda: deque(maxlen=3)))  # 🎲

@dp.message(Command("start"))
async def cmd_start(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Эта команда доступна только создателю бота.")
        return

    await message.answer(
        "🎮 Добро пожаловать в игровой конкурс!\n"
        "🎯 🎳 🎰 ⚽️ 🏀 🎲 — бросай эмодзи и зарабатывай билеты!\n"
        "📌 /time_60 — старт конкурса\n"
        "📊 /score — топ участников"
    )


@dp.message(F.text.regexp(r"^/time_(\d+)$"))
async def cmd_time(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Только создатель бота может запускать конкурс.")
        return

    match = re.match(r"^/time_(\d+)$", message.text)
    if not match:
        return

    duration = int(match.group(1))
    chat_id = message.chat.id

    if chat_id in timers:
        timers[chat_id][1].cancel()

    tickets[chat_id].clear()
    last_hits[chat_id].clear()
    cube_streaks[chat_id].clear()

    end_time = asyncio.get_event_loop().time() + duration
    task = asyncio.create_task(finish_contest(chat_id, message))
    timers[chat_id] = (end_time, task)

    await message.reply(f"⏳ Конкурс запущен на {duration} секунд! Кидай эмодзи 🎯🎳🎰🏀⚽️🎲")


@dp.message(Command("score"))
async def show_score(message: Message):
    if message.from_user.id != OWNER_ID:
        await message.reply("❌ Эта команда доступна только для владельца бота.")
        return

    chat_id = message.chat.id
    if chat_id not in tickets or not any(tickets[chat_id].values()):
        await message.reply("😢 Пока что никто не заработал билеты.")
        return

    user_scores = tickets[chat_id]
    total = sum(user_scores.values())
    leaderboard = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)

    text = "📊 <b>Топ участников:</b>\n\n"
    current_ticket = 1
    for user_id, count in leaderboard:
        start = current_ticket
        end = current_ticket + count - 1
        current_ticket = end + 1

        try:
            user = (await bot.get_chat_member(chat_id, user_id)).user
            tag = f"@{user.username}" if user.username else f"<a href='tg://user?id={user_id}'>Игрок</a>"
        except:
            tag = f"<a href='tg://user?id={user_id}'>Игрок</a>"

        percent = round(count / total * 100, 2)
        text += f"{tag} — {count} 🎟 ({percent}%) #{start}–{end}\n"

    await message.reply(text, parse_mode=ParseMode.HTML)


@dp.message(F.dice)
async def process_dice(message: Message):
    chat_id = message.chat.id
    user_id = message.from_user.id
    emoji = message.dice.emoji
    value = message.dice.value

    if chat_id not in tickets:
        return

    base = 0
    bonus = 0
    description = ""

    if emoji == "🎯":
        base = 1 if value == 1 else value * 2
        description = f"🎯 {'Промах! +1 билет' if value == 1 else f'Попадание: {value} → {base} билетов'}"

    elif emoji == "🎳":
        # Корректное сопоставление значения и сбитых кегель
        bowling_kegli = {
            1: 0,  # промах
            2: 1,
            3: 2,
            4: 3,
            5: 4,
            6: 6   # максимум
        }
        kegli = bowling_kegli.get(value, 0)
        base = 1 if kegli == 0 else kegli * 2
        description = (
            f"🎳 Промах! +1 билет" if kegli == 0
            else f"🎳 Сбито кеглей: {kegli} → {base} билетов"
        )


    elif emoji == "🎰":
        if value == 64:
            base = 200
            description = "🎰 777! +200 билетов"
        elif value == 1:
            base = 80
            description = "🎰 bar-bar-bar! +80 билетов"
        elif value in {22, 43}:
            base = 40
            description = "🎰 Три совпадения! +40 билетов"
        else:
            base = 3
            description = "🎰 Нет совпадений. +3 билета"

    elif emoji == "🏀":
        is_hit = value in {4, 5, 6}
        last_hits[chat_id][user_id].append(is_hit)
        if is_hit:
            base = 2
            if list(last_hits[chat_id][user_id]) == [True, True, True]:
                bonus = base * 10
                description = f"🏀 СТРИК 3 попаданий! x10 → +{bonus} билетов"
            else:
                description = "🏀 Попадание! +2 билета"
        else:
            base = 0
            description = "🏀 Промах! 0 билетов"

    elif emoji == "⚽️":
        is_hit = value in {3, 4, 5, 6}
        last_hits[chat_id][user_id].append(is_hit)
        if is_hit:
            base = 2
            if list(last_hits[chat_id][user_id]) == [True, True, True]:
                bonus = base * 10
                description = f"⚽️ СТРИК 3 попаданий! x10 → +{bonus} билетов"
            else:
                description = "⚽️ Попадание! +2 билета"
        else:
            base = 0
            description = "⚽️ Промах! 0 билетов"

    elif emoji == "🎲":
        cube_streaks[chat_id][user_id].append(value)
        streak_values = list(cube_streaks[chat_id][user_id])
        if len(streak_values) == 3 and len(set(streak_values)) == 1:
            base = value * 15
            description = f"🎲 СТРИК: три {value} подряд! x15 → +{base} билетов"
        else:
            base = value
            description = f"🎲 Выпало {value} → +{base} билетов"

    total = base + bonus
    if total == 0:
        return

    tickets[chat_id][user_id] += total

    username = message.from_user.username
    mention = f"@{username}" if username else f"<a href='tg://user?id={user_id}'>Игрок</a>"

    await message.reply(
        f"{description}\n{mention} теперь имеет {tickets[chat_id][user_id]} билетов.",
        parse_mode=ParseMode.HTML
    )
async def finish_contest(chat_id, message: Message):
    await asyncio.sleep(timers[chat_id][0] - asyncio.get_event_loop().time())

    user_scores = tickets.get(chat_id)
    if not any(user_scores.values()):
        await message.reply("⏰ Время вышло, но никто не заработал билеты.")
        return

    total = sum(user_scores.values())
    leaderboard = sorted(user_scores.items(), key=lambda x: x[1], reverse=True)

    text = "📊 <b>Топ участников:</b>\n\n"
    current_ticket = 1
    ticket_ranges = {}  # user_id -> (start, end)

    for user_id, count in leaderboard:
        start = current_ticket
        end = current_ticket + count - 1
        ticket_ranges[user_id] = (start, end)
        current_ticket = end + 1

        try:
            user = (await bot.get_chat_member(chat_id, user_id)).user
            tag = f"@{user.username}" if user.username else f"<a href='tg://user?id={user_id}'>Игрок</a>"
        except:
            tag = f"<a href='tg://user?id={user_id}'>Игрок</a>"

        percent = round(count / total * 100, 2)
        text += f"{tag} — {count} 🎟 ({percent}%) #{start}–{end}\n"

    # Функция для разбиения по 4000 символов
    def split_message(text, limit=4000):
        parts = []
        while len(text) > limit:
            cut = text.rfind("\n", 0, limit)
            if cut == -1:
                cut = limit
            parts.append(text[:cut])
            text = text[cut:]
        parts.append(text)
        return parts

    # Отправляем каждую часть
    for part in split_message(text):
        await message.reply(part, parse_mode=ParseMode.HTML)


    await asyncio.sleep(10)

    # Выбор победного билета
    winning_number = random.randint(1, total)
    winner_id = None

    for user_id, (start, end) in ticket_ranges.items():
        if start <= winning_number <= end:
            winner_id = user_id
            break

    winner_count = user_scores[winner_id]
    chance = round(winner_count / total * 100, 2)

    try:
        user = (await bot.get_chat_member(chat_id, winner_id)).user
        tag = f"@{user.username}" if user.username else f"<a href='tg://user?id={winner_id}'>Победитель</a>"
    except:
        tag = f"<a href='tg://user?id={winner_id}'>Победитель</a>"

    await message.reply(
        f"🏁 Победитель — {tag}!\n"
        f"🎟 Победил билет #{winning_number} из {total}\n"
        f"👑 Всего билетов: {winner_count} (шанс: {chance}%)",
        parse_mode=ParseMode.HTML
    )

    # Очистка
    tickets.pop(chat_id, None)
    timers.pop(chat_id, None)
    last_hits.pop(chat_id, None)
    cube_streaks.pop(chat_id, None)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
