"""Neta Tutor: lean Ukrainian-language Telegram lead bot (aiogram 3 + aiohttp)."""

import asyncio
import html
import logging
import os
import re
import time
from datetime import datetime, timezone

from aiohttp import ClientSession, ClientTimeout, web
from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiogram.client.default import DefaultBotProperties

from intent import infer_subject, looks_like_tutor_request


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("neta_tutor")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
ADMIN_ID_RAW = os.environ.get("ADMIN_ID", "").strip()
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PORT = int(os.environ.get("PORT", "10000"))

SUBJECTS = {
    "en": "🇬🇧 Англійська мова",
    "math": "📐 Математика",
    "nmt": "🎯 Підготовка до НМТ",
    "de": "🇩🇪 Німецька мова",
    "history": "🇺🇦 Історія України",
    "code": "💻 Програмування",
}
VALID_SOURCES = {"tiktok", "channel", "instagram", "threads", "website", "buki", "organic"}
COOLDOWN_SECONDS = 90
last_submissions: dict[int, float] = {}
last_questions: dict[int, float] = {}
router = Router()


class LeadForm(StatesGroup):
    goal = State()
    schedule = State()
    confirm = State()


class ChatForm(StatesGroup):
    message = State()


class AdminForm(StatesGroup):
    reply = State()


def esc(value: object) -> str:
    return html.escape(str(value), quote=False)


def parse_start_payload(text: str | None) -> str:
    """Limited, validated marketing attribution or preselected subject."""
    if not text:
        return "organic"
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return "organic"
    key = parts[1].strip().lower()
    if key in SUBJECTS or key in VALID_SOURCES:
        return key
    return "organic"


def subjects_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=label, callback_data=f"subject:{code}")]
        for code, label in SUBJECTS.items()
    ] + [[InlineKeyboardButton(text="↩️ На головну", callback_data="home")]])


def home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔎 Знайти репетитора", callback_data="choose")],
        [InlineKeyboardButton(text="📚 Предмети та умови", callback_data="info")],
        [InlineKeyboardButton(text="✉️ Написати викладачу", callback_data="ask")],
    ])


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Надіслати заявку", callback_data="confirm")],
        [InlineKeyboardButton(text="✏️ Заповнити заново", callback_data="choose")],
        [InlineKeyboardButton(text="❌ Скасувати", callback_data="cancel")],
    ])


def reply_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✉️ Відповісти учню", callback_data=f"reply:{user_id}")]
    ])


def privacy_text() -> str:
    return (
        "🔒 <b>Приватність Neta Tutor</b>\n\n"
        "Щоб відповісти на звернення, ми обробляємо ваш Telegram ID, "
        "ім'я та username (якщо є), обраний предмет, мету, побажання щодо часу "
        "та текст повідомлення. Заявки отримує адміністратор Neta Tutor. "
        "Якщо підключена база Supabase, ці дані також зберігаються там. "
        "Мета — організація навчання та відповіді на звернення.\n\n"
        "Не надсилайте адреси, телефони, паролі та зайві персональні дані. "
        "Команда /delete дозволяє запросити видалення даних; повідомлення, "
        "вже доставлені в чат адміністратора, потребують окремого ручного видалення. "
        "Не використовуйте бот для екстрених звернень."
    )


async def supabase_request(method: str, path: str, *, data: dict | None = None, headers: dict | None = None):
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        return None
    req_headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if headers:
        req_headers.update(headers)
    url = f"{SUPABASE_URL}/rest/v1/{path}"
    async with ClientSession(timeout=ClientTimeout(total=12)) as session:
        async with session.request(method, url, headers=req_headers, json=data) as res:
            payload = await res.text()
            if not 200 <= res.status < 300:
                raise RuntimeError(f"Supabase HTTP {res.status}: {payload[:200]}")
            return dict(status=res.status, body=payload, content_range=res.headers.get("Content-Range"))


async def go_home(msg: Message):
    await msg.answer(
        "🎓 <b>Neta Tutor — допоможемо знайти репетитора</b>\n\n"
        "Англійська, німецька, математика, історія України, "
        "програмування та підготовка до НМТ.\n\n"
        "Заняття онлайн. Залиште коротку заявку — викладач "
        "особисто відповість щодо можливості занять та вартості.",
        reply_markup=home_keyboard(),
    )


@router.message(CommandStart())
async def start_handler(message: Message, state: FSMContext):
    await state.clear()
    source = parse_start_payload(message.text)
    await state.update_data(source=source)
    await go_home(message)
    if source in SUBJECTS:
        await begin_subject(message, state, source)


@router.message(Command("myid"))
async def myid(message: Message):
    await message.answer(f"Ваш Telegram ID: <code>{message.from_user.id}</code>")


@router.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Команди: /start — головне меню; /cancel — скасувати; "
        "/privacy — приватність; /delete — запит на видалення; "
        "/myid — ваш Telegram ID.\n\n"
        "Для зв'язку з викладачем оберіть «Написати викладачу» в головному меню."
    )


@router.message(Command("privacy"))
async def privacy_handler(message: Message):
    await message.answer(privacy_text())


@router.message(Command("cancel"))
async def cancel_handler(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Дію скасовано. Повернутися: /start")


@router.message(Command("delete"))
async def delete_handler(message: Message, state: FSMContext, bot: Bot):
    uid = message.from_user.id
    await state.clear()
    last_submissions.pop(uid, None)
    last_questions.pop(uid, None)
    deleted_in_db = False
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        try:
            await supabase_request("DELETE", f"leads?telegram_id=eq.{uid}")
            deleted_in_db = True
        except Exception:
            logger.exception("Supabase deletion failed")
    try:
        await bot.send_message(
            int(ADMIN_ID_RAW),
            f"🗑 Запит на видалення даних від Telegram ID <code>{uid}</code>. "
            "Видаліть також пов'язані повідомлення з історії адмін-чату вручну."
        )
    except Exception:
        logger.exception("Failed to notify admin about deletion")
        await message.answer("⚠️ Не вдалося передати запит на видалення. Спробуйте пізніше.")
        return
    await message.answer(
        "Запит на видалення передано адміністратору. "
        + ("Записи у базі видалено. " if deleted_in_db else "")
        + "Повідомлення в чаті адміністратора потребують ручного видалення."
    )


@router.message(Command("stats"))
async def stats_handler(message: Message):
    if message.from_user.id != int(ADMIN_ID_RAW):
        return
    if not (SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY):
        await message.answer("Статистика заявок недоступна без підключеної Supabase.")
        return
    try:
        response = await supabase_request("GET", "leads?select=id&limit=1", headers={"Prefer": "count=exact"})
        raw_count = response["content_range"] or "?/невідомо"
        total = raw_count.rsplit("/", 1)[-1]
        await message.answer(f"📊 Кількість заявок у базі: <b>{esc(total)}</b>")
    except Exception:
        logger.exception("Stats failed")
        await message.answer("Помилка отримання статистики.")


@router.callback_query(F.data == "home")
async def home_cb(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    source = data.get("source", "organic")
    await state.clear()
    await state.update_data(source=source)
    await call.answer()
    await go_home(call.message)


@router.callback_query(F.data == "choose")
async def choose_cb(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    source = data.get("source", "organic")
    await state.clear()
    await state.update_data(source=source)
    await call.answer()
    await call.message.answer("📚 <b>Який предмет вас цікавить?</b>", reply_markup=subjects_keyboard())


@router.callback_query(F.data == "info")
async def info_cb(call: CallbackQuery):
    await call.answer()
    await call.message.answer(
        "📚 <b>Напрями навчання</b>\n\n"
        "🇬🇧 Англійська\n📐 Математика\n🎯 НМТ\n🇩🇪 Німецька\n"
        "🇺🇦 Історія України\n💻 Програмування\n\n"
        "💻 Формат: онлайн, індивідуально.\n"
        "💳 Ціна, тривалість і графік узгоджуються з викладачем "
        "перед початком занять.\n\n"
        "Натисніть /start, щоб залишити заявку."
    )


async def begin_subject(message: Message, state: FSMContext, code: str):
    data = await state.get_data()
    source = data.get("source", "organic")
    await state.clear()
    await state.set_state(LeadForm.goal)
    await state.update_data(source=source, subject=code)
    await message.answer(
        f"Обрано: <b>{esc(SUBJECTS[code])}</b>\n\n"
        "✍️ <b>Крок 2/3.</b> Для кого заняття і яка мета?\n"
        "Наприклад: «10 клас, готуюся до НМТ» або «дорослий, німецька з нуля».\n\n"
        "Не вказуйте приватні контакти чи адресу. /cancel — скасувати."
    )


@router.callback_query(F.data.startswith("subject:"))
async def subject_cb(call: CallbackQuery, state: FSMContext):
    code = call.data.partition(":")[2]
    await call.answer()
    if code not in SUBJECTS:
        await call.message.answer("Невідомий предмет. Спробуйте /start")
        return
    await begin_subject(call.message, state, code)


@router.message(LeadForm.goal, F.text)
async def goal_handler(message: Message, state: FSMContext):
    goal = message.text.strip()
    if not 3 <= len(goal) <= 350:
        await message.answer("Опишіть мету коротко — від 3 до 350 символів.")
        return
    await state.update_data(goal=goal)
    await state.set_state(LeadForm.schedule)
    await message.answer(
        "🕒 <b>Крок 3/3.</b> Коли вам зручно займатися?\n"
        "Наприклад: «вівторок/четвер після 17:00» або «будь-який вечір»."
    )


@router.message(LeadForm.schedule, F.text)
async def schedule_handler(message: Message, state: FSMContext):
    schedule = message.text.strip()
    if not 2 <= len(schedule) <= 250:
        await message.answer("Напишіть бажаний час — від 2 до 250 символів.")
        return
    await state.update_data(schedule=schedule)
    await state.set_state(LeadForm.confirm)
    data = await state.get_data()
    subject = SUBJECTS[data["subject"]]
    await message.answer(
        "🧾 <b>Перевірте заявку</b>\n\n"
        f"Предмет: <b>{esc(subject)}</b>\n"
        f"Мета: {esc(data['goal'])}\n"
        f"Зручний час: {esc(schedule)}\n\n"
        "Натискаючи «Надіслати заявку», ви погоджуєтеся "
        "передати ці дані адміністратору Neta Tutor для зв'язку. "
        "Правила: /privacy",
        reply_markup=confirm_keyboard(),
    )


@router.callback_query(F.data == "confirm")
async def confirm_cb(call: CallbackQuery, state: FSMContext, bot: Bot):
    uid = call.from_user.id
    current = await state.get_state()
    if current != LeadForm.confirm.state:
        await call.answer("Заявка вже оброблена або застаріла. /start", show_alert=True)
        return
    now = time.monotonic()
    if now - last_submissions.get(uid, -10**9) < COOLDOWN_SECONDS:
        await call.answer("Зачекайте трохи перед новою заявкою.", show_alert=True)
        return
    data = await state.get_data()
    if not all(key in data for key in ("subject", "goal", "schedule")):
        await call.answer("Дані застаріли. Заповніть форму знову: /start", show_alert=True)
        return
    user = call.from_user
    username = f"@{user.username}" if user.username else "немає"
    card = (
        "🔔 <b>Нова заявка Neta Tutor</b>\n"
        f"ID користувача: <code>{uid}</code>\n"
        f"Ім'я: {esc(user.full_name)}\n"
        f"Username: {esc(username)}\n"
        f"Предмет: <b>{esc(SUBJECTS[data['subject']])}</b>\n"
        f"Мета: {esc(data['goal'])}\n"
        f"Коли зручно: {esc(data['schedule'])}\n"
        f"Джерело: {esc(data.get('source', 'organic'))}\n\n"
        "Щоб відповісти, натисніть кнопку або дайте відповідь саме на це повідомлення."
    )
    try:
        await bot.send_message(int(ADMIN_ID_RAW), card, reply_markup=reply_keyboard(uid))
    except Exception:
        logger.exception("Delivery of lead to admin failed")
        await call.answer("Не вдалось надіслати заявку. Спробуйте пізніше.", show_alert=True)
        return
    last_submissions[uid] = now
    await state.clear()
    await call.answer("Заявку надіслано!")
    await call.message.answer(
        "✅ <b>Заявка надіслана!</b>\n\n"
        "Викладач ознайомиться з нею і відповість вам у цьому боті. "
        "Точний час відповіді не гарантовано.\n\n"
        "Нова заявка: /start"
    )
    if SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY:
        record = {
            "telegram_id": uid,
            "telegram_username": user.username,
            "display_name": user.full_name[:200],
            "subject": data["subject"],
            "goal": data["goal"],
            "schedule": data["schedule"],
            "source": data.get("source", "organic"),
            "status": "new",
        }
        try:
            await supabase_request("POST", "leads", data=record, headers={"Prefer": "return=minimal"})
        except Exception:
            logger.exception("Failed to persist lead; admin already notified")


@router.callback_query(F.data == "cancel")
async def cancel_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.answer("Заявку скасовано. /start — головне меню.")


@router.callback_query(F.data == "ask")
async def ask_cb(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await state.set_state(ChatForm.message)
    await call.answer()
    await call.message.answer("✉️ Напишіть одне повідомлення викладачу (до 800 символів). /cancel — скасувати.")


@router.message(ChatForm.message, F.text)
async def user_chat(message: Message, state: FSMContext, bot: Bot):
    message_text = message.text.strip()
    if not 1 <= len(message_text) <= 800:
        await message.answer("Повідомлення має бути від 1 до 800 символів.")
        return
    uid = message.from_user.id
    now = time.monotonic()
    if now - last_questions.get(uid, -10**9) < 60:
        await message.answer("Зачекайте хвилину перед наступним повідомленням.")
        return
    try:
        await bot.send_message(
            int(ADMIN_ID_RAW),
            "💬 <b>Повідомлення учня</b>\n"
            f"ID користувача: <code>{uid}</code>\n"
            f"Ім'я: {esc(message.from_user.full_name)}\n\n"
            f"{esc(message_text)}",
            reply_markup=reply_keyboard(uid),
        )
    except Exception:
        logger.exception("Could not send learner message")
        await message.answer("Повідомлення зараз не доставлено. Спробуйте пізніше.")
        return
    last_questions[uid] = now
    await state.clear()
    await message.answer("✅ Повідомлення відправлено. Повернутися: /start")


@router.callback_query(F.data.startswith("reply:"))
async def admin_reply_cb(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != int(ADMIN_ID_RAW):
        await call.answer("Недоступно", show_alert=True)
        return
    uid_text = call.data.partition(":")[2]
    if not uid_text.isdecimal():
        await call.answer("Некоректний ID", show_alert=True)
        return
    await state.clear()
    await state.set_state(AdminForm.reply)
    await state.update_data(reply_to=int(uid_text))
    await call.answer()
    await call.message.answer(f"✉️ Напишіть відповідь для користувача <code>{uid_text}</code>. /cancel — скасувати.")


@router.message(AdminForm.reply, F.text)
async def admin_reply_handler(message: Message, state: FSMContext, bot: Bot):
    if message.from_user.id != int(ADMIN_ID_RAW):
        return
    data = await state.get_data()
    uid = data.get("reply_to")
    if not uid:
        await message.answer("Не вдалося визначити адресата. /cancel")
        return
    if len(message.text) > 3000:
        await message.answer("Надто довге повідомлення (максимум 3000 символів).")
        return
    await send_admin_reply(message, bot, int(uid), message.text)
    await state.clear()


async def send_admin_reply(message: Message, bot: Bot, uid: int, body: str):
    try:
        await bot.send_message(uid, "💬 <b>Відповідь від Neta Tutor</b>\n\n" + esc(body))
        await message.answer("✅ Відправлено учню.")
    except Exception:
        logger.exception("Admin reply failed")
        await message.answer("⚠️ Не вдалося доставити повідомлення (учень міг заблокувати бота).")


@router.message(F.reply_to_message, F.text)
async def admin_reply_to_card(message: Message, bot: Bot):
    if message.from_user.id != int(ADMIN_ID_RAW):
        return
    referred = message.reply_to_message
    if not referred or not referred.from_user or not referred.from_user.is_bot:
        return
    match = re.search(r"ID користувача:\s*(\d+)", referred.text or "")
    if not match:
        return
    if len(message.text) > 3000:
        await message.answer("Відповідь завелика (максимум 3000 символів).")
        return
    await send_admin_reply(message, bot, int(match.group(1)), message.text)


@router.message()
async def fallback_handler(message: Message, state: FSMContext):
    if message.chat.type != "private":
        return
    current = await state.get_state()
    if current:
        await message.answer("Будь ласка, надішліть текст. Або натисніть /cancel.")
        return
    if message.text:
        subject = infer_subject(message.text)
        if subject:
            data = await state.get_data()
            source = data.get("source", "organic")
            await state.clear()
            await state.set_state(LeadForm.schedule)
            await state.update_data(
                source=source, subject=subject, goal=message.text.strip()[:350]
            )
            await message.answer(
                f"Зрозуміло! Предмет: <b>{esc(SUBJECTS[subject])}</b>\n\n"
                "Коли вам зручно займатися? Наприклад: «у будні після 17:00». "
                "Далі підтвердимо вашу заявку."
            )
            return
        if looks_like_tutor_request(message.text):
            await message.answer("Оберіть предмет, і допоможу залишити заявку:", reply_markup=subjects_keyboard())
            return
    await message.answer("Оберіть потрібну дію через /start. Напишіть /help для довідки.")


def make_health_app() -> web.Application:
    app = web.Application()

    async def health(_request: web.Request):
        return web.json_response({"status": "ok", "service": "neta-tutor"})

    async def index(_request: web.Request):
        return web.Response(text="Neta Tutor bot service. Check /health.", content_type="text/plain")

    app.router.add_get("/health", health)
    app.router.add_get("/", index)
    return app


async def main():
    if not BOT_TOKEN:
        raise RuntimeError("Set BOT_TOKEN in Render environment or .env")
    if not ADMIN_ID_RAW.isdecimal():
        raise RuntimeError("ADMIN_ID must be a numeric Telegram user ID")
    if bool(SUPABASE_URL) != bool(SUPABASE_SERVICE_ROLE_KEY):
        raise RuntimeError("Set both SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY (or neither)")

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(router)
    app = make_health_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logger.info("Health server running on port %d", PORT)

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Знайти репетитора"),
            BotCommand(command="help", description="Допомога"),
            BotCommand(command="privacy", description="Приватність"),
            BotCommand(command="delete", description="Запит на видалення даних"),
            BotCommand(command="cancel", description="Скасувати дію"),
        ])
        await bot.delete_webhook(drop_pending_updates=False)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await runner.cleanup()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
