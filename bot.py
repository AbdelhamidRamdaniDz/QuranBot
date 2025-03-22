import time
import logging
import requests
from pyrogram import Client, filters
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)
from dotenv import load_dotenv
import os
load_dotenv()  

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_API_URL = os.getenv("BASE_API_URL")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

app = Client(
    "quran_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    ipv6=False
)

CACHE = {
    "reciters": {"data": None, "timestamp": 0},
    "chapters": {"data": None, "timestamp": 0}
}
CACHE_TTL = 3600

def get_cached_data(key, fetch_func):
    now = time.time()
    if not CACHE[key]["data"] or (now - CACHE[key]["timestamp"] > CACHE_TTL):
        CACHE[key]["data"] = fetch_func()
        CACHE[key]["timestamp"] = now
    return CACHE[key]["data"]

playback_states = {}

def get_user_state(user_id):
    if user_id not in playback_states:
        playback_states[user_id] = {
            "current_reciter": None,
            "current_chapter": None,
            "audio_message_id": None
        }
    return playback_states[user_id]

def fetch_reciters():
    url = f"{BASE_API_URL}/resources/recitations"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            return [{"id": r["id"], "name": r["reciter_name"]} for r in data.get("recitations", [])]
        else:
            logger.error(f"فشل في جلب قائمة القراء: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"خطأ في الاتصال (reciters): {str(e)}")
        return []

def fetch_chapters():
    url = f"{BASE_API_URL}/chapters?language=ar"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            return data.get("chapters", [])
        else:
            logger.error(f"فشل في جلب قائمة السور: {response.status_code}")
            return []
    except Exception as e:
        logger.error(f"خطأ في الاتصال (chapters): {str(e)}")
        return []

def fetch_audio_url(reciter_id, chapter_number):
    url = f"{BASE_API_URL}/chapter_recitations/{reciter_id}/{chapter_number}"
    try:
        response = requests.get(url, timeout=10)
        if response.ok:
            data = response.json()
            audio_file = data.get("audio_file", {})
            return audio_file.get("audio_url"), audio_file.get("file_size", 0)
        else:
            logger.error(f"فشل في جلب رابط السورة: {response.status_code}")
            return None, 0
    except Exception as e:
        logger.error(f"خطأ في الاتصال (audio): {str(e)}")
        return None, 0

@app.on_message(filters.command("start"))
async def start_cmd(client: Client, message: Message):
    text = (
        "🕌 أهلًا بك في بوت تشغيل القرآن!\n\n"
        "الأوامر:\n"
        "/start - بدء المحادثة\n"
        "/play - بدء التشغيل\n"
        "/help - عرض التعليمات\n\n"
        "ملاحظة: لتعيين البوت مشرفًا في المجموعة، يجب على أحد مشرفي المجموعة رفعه يدويًا."
    )
    await message.reply(text)

@app.on_message(filters.command("help"))
async def help_cmd(client: Client, message: Message):
    text = (
        "**تعليمات البوت:**\n"
        "- استخدم /play لبدء التشغيل.\n"
        "- أولاً، ستظهر لك قائمة بالقرّاء؛ اختر القارئ المطلوب.\n"
        "- بعدها ستظهر قائمة السور؛ اختر السورة المطلوبة.\n"
        "- بعد بدء التشغيل، يمكنك التحكم بالتسجيل عبر أزرار (إيقاف مؤقت، استئناف، السورة التالية، رجوع).\n"
        "- إذا كان الملف أكبر من 50 ميجابايت، سيتم إرسال الرابط بدلاً من تشغيل الملف.\n\n"
        "✅ للاستفسار والدعم: [الدعم الفني](https://t.me/QuranSupport)"
    )
    await message.reply(text)

@app.on_message(filters.command("play"))
async def play_cmd(client: Client, message: Message):
    reciters = get_cached_data("reciters", fetch_reciters)
    if not reciters:
        await message.reply("⚡ تعذر جلب قائمة القراء، يرجى المحاولة لاحقًا.")
        return

    buttons = [
        [InlineKeyboardButton(reciter["name"], callback_data=f"rec_{reciter['id']}")]
        for reciter in reciters
    ]
    buttons.append([InlineKeyboardButton("إغلاق ❌", callback_data="close")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await message.reply("🎙 اختر القارئ:", reply_markup=reply_markup)

@app.on_callback_query(filters.regex(r"^rec_(\d+)$"))
async def reciter_selected(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    reciter_id = int(callback.data.split("_")[1])
    state["current_reciter"] = reciter_id

    chapters = get_cached_data("chapters", fetch_chapters)
    if not chapters:
        await callback.answer("❌ تعذر جلب قائمة السور", show_alert=True)
        return

    buttons = [
        [InlineKeyboardButton(f"{ch['id']}. {ch['name_arabic']}", callback_data=f"ch_{ch['id']}")]
        for ch in chapters
    ]
    buttons.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_to_start")])
    reply_markup = InlineKeyboardMarkup(buttons)
    await callback.message.edit_text("📖 اختر السورة:", reply_markup=reply_markup)

@app.on_callback_query(filters.regex(r"^back_to_start$"))
async def back_to_start_cmd(client: Client, callback: CallbackQuery):
    await callback.message.edit_text("🔙 العودة إلى القائمة الرئيسية. استخدم /play لعرض قائمة القراء مرة أخرى.")

@app.on_callback_query(filters.regex(r"^ch_(\d+)$"))
async def chapter_selected(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    chapter_id = int(callback.data.split("_")[1])
    state["current_chapter"] = chapter_id

    if state["current_reciter"] is None:
        await callback.answer("❌ يرجى اختيار قارئ أولاً", show_alert=True)
        return

    audio_link, file_size = fetch_audio_url(state["current_reciter"], chapter_id)
    if not audio_link:
        await callback.answer("❌ تعذر جلب رابط التسجيل", show_alert=True)
        return

    max_size = 50 * 1024 * 1024 
    if file_size is not None and file_size > max_size:
        text = (
            f"❗ الملف كبير جدًا ({file_size/1024/1024:.2f}MB).\n"
            f"يمكنك الاستماع إليه عبر الرابط التالي:\n{audio_link}"
        )
        await callback.message.edit_text(text)
    else:
        try:
            sent_audio = await client.send_audio(
                chat_id=callback.message.chat.id,
                audio=audio_link,
                title=f"سورة {chapter_id}",
                performer=f"القارئ {state['current_reciter']}"
            )
            state["audio_message_id"] = sent_audio.id
            controls = InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("⏸ إيقاف", callback_data="pause"),
                    InlineKeyboardButton("▶️ استئناف", callback_data="resume")
                ],
                [
                    InlineKeyboardButton("⏭ تالي", callback_data="next"),
                    InlineKeyboardButton("↩️ رجوع", callback_data="back_to_chapters")
                ]
            ])
            await callback.message.edit_text(
                f"🔊 جاري تشغيل سورة {chapter_id} بصوت القارئ {state['current_reciter']}.",
                reply_markup=controls
            )
        except Exception as e:
            err = str(e)
            logger.error(f"خطأ في تشغيل السورة: {err}")
            if "WEBPAGE_MEDIA_EMPTY" in err or "WEBPAGE_CURL_FAILED" in err:
                await callback.message.edit_text(
                    f"❗ تعذر تشغيل التسجيل بسبب مشكلة في الملف.\n"
                    f"يمكنك الاستماع إليه عبر الرابط:\n{audio_link}"
                )
            else:
                await callback.message.edit_text("❌ فشل في تشغيل السورة.")

@app.on_callback_query(filters.regex(r"^(pause|resume|next|back_to_chapters|close)$"))
async def control_buttons(client: Client, callback: CallbackQuery):
    user_id = callback.from_user.id
    state = get_user_state(user_id)
    action = callback.data

    if action == "close":
        await callback.message.delete()

    elif action == "pause":
        if state.get("audio_message_id"):
            try:
                await client.delete_messages(
                    chat_id=callback.message.chat.id,
                    message_ids=state["audio_message_id"]
                )
                await callback.answer("✅ تم الإيقاف المؤقت", show_alert=True)
            except Exception as e:
                logger.error(f"خطأ في الإيقاف: {str(e)}")
                await callback.answer("❌ فشل في الإيقاف", show_alert=True)

    elif action == "resume":
        if state.get("current_chapter") and state.get("current_reciter"):
            audio_link, file_size = fetch_audio_url(state["current_reciter"], state["current_chapter"])
            if audio_link:
                try:
                    sent_audio = await client.send_audio(
                        chat_id=callback.message.chat.id,
                        audio=audio_link,
                        title=f"سورة {state['current_chapter']}",
                        performer=f"القارئ {state['current_reciter']}"
                    )
                    state["audio_message_id"] = sent_audio.id
                    await callback.answer("✅ تم استئناف التشغيل", show_alert=True)
                except Exception as e:
                    logger.error(f"خطأ في الاستئناف: {str(e)}")
                    await callback.answer("❌ فشل في استئناف التشغيل", show_alert=True)
        else:
            await callback.answer("❌ لا توجد سورة قيد التشغيل", show_alert=True)

    elif action == "next":
        chapters = get_cached_data("chapters", fetch_chapters)
        current = state.get("current_chapter", 0)
        next_chapter = next((ch for ch in chapters if ch["id"] > current), None)
        if next_chapter:
            state["current_chapter"] = next_chapter["id"]
            audio_link, file_size = fetch_audio_url(state["current_reciter"], next_chapter["id"])
            if audio_link:
                try:
                    sent_audio = await client.send_audio(
                        chat_id=callback.message.chat.id,
                        audio=audio_link,
                        title=f"سورة {next_chapter['id']}",
                        performer=f"القارئ {state['current_reciter']}"
                    )
                    state["audio_message_id"] = sent_audio.id
                    await callback.message.edit_text(
                        f"🔊 جاري تشغيل سورة {next_chapter['id']} بصوت القارئ {state['current_reciter']}."
                    )
                    await callback.answer("✅ تم تشغيل السورة التالية", show_alert=True)
                except Exception as e:
                    logger.error(f"خطأ في تشغيل السورة التالية: {str(e)}")
                    await callback.answer("❌ فشل في تشغيل السورة التالية", show_alert=True)
            else:
                await callback.answer("❌ تعذر جلب رابط التسجيل للسورة التالية", show_alert=True)
        else:
            await callback.answer("❌ لا توجد سورة تالية", show_alert=True)

    elif action == "back_to_chapters":
        chapters = get_cached_data("chapters", fetch_chapters)
        if not chapters:
            await callback.answer("❌ تعذر جلب قائمة السور", show_alert=True)
            return
        buttons = [
            [InlineKeyboardButton(f"{ch['id']}. {ch['name_arabic']}", callback_data=f"ch_{ch['id']}")]
            for ch in chapters
        ]
        buttons.append([InlineKeyboardButton("↩️ رجوع", callback_data="back_to_start")])
        reply_markup = InlineKeyboardMarkup(buttons)
        await callback.message.edit_text("📖 اختر السورة:", reply_markup=reply_markup)

@app.on_callback_query(filters.regex(r"^back_to_start$"))
async def back_to_start(client: Client, callback: CallbackQuery):
    await callback.message.edit_text("🔙 العودة إلى القائمة الرئيسية. استخدم /play لعرض قائمة القراء مرة أخرى.")

if __name__ == "__main__":
    logger.info("جارٍ تشغيل البوت باستخدام Pyrogram وMTProto API...")
    app.run()