import threading
from flask import Flask
import os
import json
import logging
import random
import asyncio
from pathlib import Path

from telegram import (
    Update, InlineKeyboardButton, InlineKeyboardMarkup,
    KeyboardButton, ReplyKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters, ContextTypes
)
from telegram.constants import ChatAction, ParseMode
import google.generativeai as genai
from PIL import Image

# ==================== تنظیمات ====================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# خواندن توکن‌ها از متغیرهای محیطی برای امنیت کامل در گیت‌هاب
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """تو "نورا" هستی، یه دستیار هوش مصنوعی پیشرفته و دوست‌داشتنی.

ویژگی‌های شخصیتی:
- به فارسی محاوره‌ای و گرم صحبت می‌کنی
- صادق، باهوش، کمی شوخ‌طبع
- جواب‌ها کوتاه و کاربردی (مگه کاربر بخواد بلند باشه)
- ایموجی کم ولی با‌معنا
- اگه نمی‌دونی، صادق بگو
- توانایی: ترجمه، کدنویسی، تحلیل، خلاقیت، آموزش، خلاصه‌سازی"""

MODELS = {
    "default": "gemini-flash-lite-latest",
    "vision": "gemini-flash-lite-latest",
}

MODES = {
    "normal":   {"temp": 0.7, "desc": "متعادل"},
    "creative": {"temp": 1.1, "desc": "خلاقانه"},
    "precise":  {"temp": 0.2, "desc": "دقیق"},
    "short":    {"temp": 0.4, "desc": "کوتاه"},
}

DATA_DIR = Path("user_data")
TEMP_DIR = Path("temp")
DATA_DIR.mkdir(exist_ok=True)
TEMP_DIR.mkdir(exist_ok=True)


def load_user(user_id: int) -> dict:
    file = DATA_DIR / f"{user_id}.json"
    if file.exists():
        try:
            return json.loads(file.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "history": [],
        "mode": "normal",
        "name": None,
    }


def save_user(user_id: int, data: dict):
    file = DATA_DIR / f"{user_id}.json"
    file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def trim_history(history: list, max_turns: int = 15) -> list:
    return history[-(max_turns * 2):]


def get_model(mode: str = "normal"):
    config = MODES.get(mode, MODES["normal"])
    return genai.GenerativeModel(
        model_name=MODELS["default"],
        system_instruction=SYSTEM_PROMPT,
        generation_config={
            "temperature": config["temp"],
            "max_output_tokens": 2048,
        }
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    data = load_user(user.id)
    data["name"] = user.first_name
    save_user(user.id, data)

    keyboard = ReplyKeyboardMarkup(
        [
            [KeyboardButton("💬 چت جدید"), KeyboardButton("🎨 حالت خلاق")],
            [KeyboardButton("📊 حالت دقیق"), KeyboardButton("⚡ پاسخ کوتاه")],
            [KeyboardButton("📝 خلاصه"), KeyboardButton("💻 کدنویسی")],
            [KeyboardButton("🌐 ترجمه"), KeyboardButton("ℹ️ راهنما")],
        ],
        resize_keyboard=True,
        input_field_placeholder="هر چیزی بپرس..."
    )

    await update.message.reply_text(
        f"سلام {user.first_name}! 👋✨\n\n"
        "من **نورا** هستم، دستیار هوش مصنوعی تو.\n"
        "هر سوالی داری بپرس یا از منوی پایین استفاده کن.\n\n"
        "🧠 قابلیت‌ها:\n"
        "• عکس بفرست → تحلیل می‌کنم\n"
        "• صدا بفرست → متنش رو می‌نویسم\n"
        "• کدنویسی، ترجمه، خلاصه و ...\n\n"
        "⚠️ جواب‌های من ممکنه اشتباه باشن.",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📚 **راهنمای نورا**\n\n"
        "**دستورات:**\n"
        "• `/start` — شروع و منو\n"
        "• `/clear` — پاک کردن حافظه\n"
        "• `/mode` — تغییر حالت پاسخ\n"
        "• `/stats` — آمار استفاده\n\n"
        "**قابلیت‌ها:**\n"
        "• 📷 عکس بفرست → تحلیل\n"
        "• 🎤 صدا بفرست → تبدیل به متن\n"
        "• 📝 `خلاصه: متن`\n"
        "• 💻 `کد: درخواست`\n"
        "• 🌐 `ترجمه به انگلیسی: متن`\n\n"
        "**حالت‌ها:**\n"
        "• 💬 عادی — متعادل\n"
        "• 🎨 خلاق — ایده‌های جدید\n"
        "• 📊 دقیق — واقع‌بینانه\n"
        "• ⚡ کوتاه — خلاصه و سریع"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_user(user_id)
    data["history"] = []
    save_user(user_id, data)
    await update.message.reply_text("🧹 حافظه پاک شد! از نو شروع کنیم.")


async def mode_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💬 عادی", callback_data="mode_normal"),
            InlineKeyboardButton("🎨 خلاق", callback_data="mode_creative"),
        ],
        [
            InlineKeyboardButton("📊 دقیق", callback_data="mode_precise"),
            InlineKeyboardButton("⚡ کوتاه", callback_data="mode_short"),
        ],
    ])
    await update.message.reply_text("🎯 حالت پاسخ‌گویی رو انتخاب کن:", reply_markup=keyboard)


async def stats_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = load_user(user_id)
    history = data.get("history", [])
    user = update.effective_user

    await update.message.reply_text(
        f"📊 **آمار شما**\n\n"
        f"👤 نام: {user.first_name}\n"
        f"💬 تعداد پیام‌ها: {len(history) // 2}\n"
        f"🎯 حالت فعلی: `{data.get('mode', 'normal')}`\n"
        f"💾 وضعیت: ذخیره شده",
        parse_mode=ParseMode.MARKDOWN
    )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("mode_"):
        new_mode = query.data.replace("mode_", "")
        user_id = update.effective_user.id
        user_data = load_user(user_id)
        user_data["mode"] = new_mode
        save_user(user_id, user_data)

        mode_names = {
            "normal": "💬 عادی",
            "creative": "🎨 خلاق",
            "precise": "📊 دقیق",
            "short": "⚡ کوتاه"
        }
        await query.edit_message_text(
            f"✅ حالت به **{mode_names.get(new_mode, new_mode)}** تغییر کرد!",
            parse_mode=ParseMode.MARKDOWN
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()
    data = load_user(user_id)

    menu_actions = {
        "💬 چت جدید": "clear",
        "🎨 حالت خلاق": "mode_creative",
        "📊 حالت دقیق": "mode_precise",
        "⚡ پاسخ کوتاه": "mode_short",
        "📝 خلاصه": "prompt_summary",
        "💻 کدنویسی": "prompt_code",
        "🌐 ترجمه": "prompt_translate",
        "ℹ️ راهنما": "help",
    }

    if text in menu_actions:
        action = menu_actions[text]

        if action == "clear":
            data["history"] = []
            save_user(user_id, data)
            await update.message.reply_text("🧹 حافظه پاک شد!")
            return

        if action == "help":
            await help_cmd(update, context)
            return

        if action.startswith("mode_"):
            mode = action.replace("mode_", "")
            data["mode"] = mode
            save_user(user_id, data)
            mode_names = {
                "creative": "🎨 خلاق",
                "precise": "📊 دقیق",
                "short": "⚡ کوتاه"
            }
            await update.message.reply_text(
                f"✅ حالت به **{mode_names.get(mode)}** تغییر کرد!",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if action == "prompt_summary":
            await update.message.reply_text("📝 متنی که می‌خوای خلاصه کنم رو بفرست، یا بنویس:\n`خلاصه: متن`")
            return
        if action == "prompt_code":
            await update.message.reply_text("💻 بگو چه کدی می‌خوای؟ (زبان + کارش چی باشه)")
            return
        if action == "prompt_translate":
            await update.message.reply_text("🌐 متن رو بفرست یا بنویس:\n`ترجمه به انگلیسی: متن`")
            return

    await process_ai_request(update, context, text)


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    photo = update.message.photo[-1]
    file = await context.bot.get_file(photo.file_id)
    local_path = TEMP_DIR / f"{photo.file_id}.jpg"

    try:
        await file.download_to_drive(str(local_path))
        img = Image.open(local_path)
        caption = update.message.caption or "این عکس رو توصیف و تحلیل کن."
        await process_ai_request(update, context, caption, image=img)
    finally:
        if local_path.exists():
            local_path.unlink(missing_ok=True)


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    voice = update.message.voice
    file = await context.bot.get_file(voice.file_id)
    local_path = TEMP_DIR / f"{voice.file_id}.ogg"

    try:
        await file.download_to_drive(str(local_path))
        audio_file = genai.upload_file(str(local_path))

        model = genai.GenerativeModel(MODELS["default"])
        response = model.generate_content([
            "این فایل صوتی رو به متن فارسی تبدیل کن. فقط متن رو بنویس، هیچ توضیح اضافه‌ای نده.",
            audio_file
        ])
        text = response.text.strip()

        await update.message.reply_text(
            f"🎤 **متن پیام صوتی:**\n\n{text}",
            parse_mode=ParseMode.MARKDOWN
        )

        await process_ai_request(
            update, context,
            f"کاربر این پیام صوتی رو فرستاده:\n\n«{text}»\n\nاگه لازم بود در موردش حرف بزن یا کمک کن."
        )

        try:
            genai.delete_file(audio_file.name)
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Voice error: {e}")
        await update.message.reply_text("⚠️ خطا در پردازش صدا. دوباره امتحان کن.")
    finally:
        if local_path.exists():
            local_path.unlink(missing_ok=True)


async def process_ai_request(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, image=None):
    user_id = update.effective_user.id
    data = load_user(user_id)
    mode = data.get("mode", "normal")

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    try:
        model = get_model(mode)
        history = data.get("history", [])
        chat = model.start_chat(history=history)

        content = [text, image] if image is not None else text
        response = chat.send_message(content, stream=True)

        full_text = ""
        sent_message = None
        last_edit = 0

        for chunk in response:
            if not chunk.text:
                continue
            full_text += chunk.text

            now = asyncio.get_event_loop().time()
            if sent_message is None:
                sent_message = await update.message.reply_text(full_text + " ▌")
                last_edit = now
            elif now - last_edit > 0.85:
                try:
                    await sent_message.edit_text(full_text + " ▌")
                    last_edit = now
                except Exception:
                    pass

        if sent_message:
            try:
                await sent_message.edit_text(full_text)
            except Exception:
                await update.message.reply_text(full_text)
        else:
            await update.message.reply_text(full_text or "🤔 پاسخی دریافت نشد.")

        if image is None and full_text:
            data["history"].append({"role": "user", "parts": [text]})
            data["history"].append({"role": "model", "parts": [full_text]})
            data["history"] = trim_history(data["history"])
            save_user(user_id, data)

        if len(full_text) > 80 and random.random() < 0.25:
            try:
                await update.message.reply_reaction(random.choice(["👍", "❤️", "🔥", "✨"]))
            except Exception:
                pass

    except Exception as e:
        logger.error(f"AI Error: {e}", exc_info=True)
        await update.message.reply_text(
            "⚠️ یه مشکلی پیش اومد. لطفاً دوباره امتحان کن.\n"
            "اگه ادامه داشت `/clear` بزن."
        )


def main():
    if not TELEGRAM_TOKEN:
        logger.error("TELEGRAM_TOKEN is missing!")
        return

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("mode", mode_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("🤖 نورا فعال شد...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


# راه‌اندازی سرور وب در کنار ربات
app = Flask(__name__)


@app.route("/")
def home():
  return "Nora AI Server is Running & Online!"


def run_web():
  port = int(os.environ.get("PORT", 8080))
  app.run(host="0.0.0.0", port=port)


if __name__ == "__main__":
  # اجرای وب‌سایت در پس‌زمینه
  web_thread = threading.Thread(target=run_web)
  web_thread.start()

  # اجرای ربات اصلی نورا
  main()

