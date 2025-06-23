import logging
import aiosqlite
from datetime import datetime, timedelta
from functools import wraps
import nest_asyncio
import random
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ================= CONFIG =================
nest_asyncio.apply()
BOT_TOKEN = "7968460286:AAEE1qexfwtMyvuyO0u4bRiby_-teEZNL44"
ADMINS = {5235901291, 1679338579, 6509833002}
MAIN_ADMIN_USERNAME = "@Amiraly7"
DB_FILE = "vpn_bot.db"
CHANNELS = [
    "@arshiashi",
]

WELCOME_TEXT = (
    "✨ به ربات configs. خوش آمدید! ✨\n\n"
    "این ربات جهت ارائه کانفیگ‌های با کیفیت و مصرف منصفانه توسعه داده شده است.\n"
    "برای استفاده از ربات، ابتدا باید در کانال‌ ما عضو شوید:\n"
    f"{chr(10).join(CHANNELS)}\n\n"
    "پس از عضویت، می‌توانید از خدمات ربات استفاده کنید."
)
# =========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

admin_states = {}
user_states = {}

async def init_db():
    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                last_daily_receive TIMESTAMP
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS configs (
                name TEXT PRIMARY KEY,
                type TEXT,
                link TEXT,
                code TEXT
            )
            """
        )
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS usage (
                config_name TEXT PRIMARY KEY,
                used INTEGER,
                FOREIGN KEY (config_name) REFERENCES configs(name)
            )
            """
        )
        await db.commit()

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS

def admin_only(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not is_admin(user.id):
            await update.message.reply_text("❌ دسترسی فقط برای ادمین‌ها مجاز است.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def check_channel_membership(user_id: int, context: ContextTypes.DEFAULT_TYPE) -> bool:
    for channel in CHANNELS:
        try:
            member = await context.bot.get_chat_member(channel, user_id)
            if member.status not in {"member", "administrator", "creator"}:
                return False
        except Exception as e:
            logger.warning(f"خطا در بررسی عضویت کانال {channel} برای کاربر {user_id}: {e}")
            return False
    return True

def main_keyboard(is_admin=False):
    buttons = [
        ["📩 دریافت کانفیگ روزانه", "🚨 دریافت کانفیگ اضطراری"],
        ["🛒 خرید کانفیگ اختصاصی", "ℹ️ راهنما"]
    ]
    if is_admin:
        buttons.append(["➕ افزودن کانفیگ جدید"])
    return ReplyKeyboardMarkup(
        buttons,
        resize_keyboard=True,
        one_time_keyboard=False,
        selective=True,
    )

def back_keyboard():
    return ReplyKeyboardMarkup(
        [["🔙 بازگشت"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

def config_type_keyboard():
    return ReplyKeyboardMarkup(
        [["Daily", "Emergency"], ["🔙 بازگشت"]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    is_member = await check_channel_membership(user.id, context)
    if not is_member:
        await update.message.reply_text(
            "⚠️ لطفا ابتدا عضو کانال‌های ما شوید تا بتوانید از ربات استفاده کنید:\n"
            + "\n".join(CHANNELS)
        )
        return

    async with aiosqlite.connect(DB_FILE) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users(user_id, last_daily_receive) VALUES (?, NULL)",
            (user.id,)
        )
        await db.commit()

    await update.message.reply_text(
        "سلام! 🌟\n\n"
        "ربات configs. آماده خدمت‌رسانی به شماست! 🔐\n"
        "لطفا از دکمه‌های زیر برای دریافت خدمات استفاده کنید.",
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
    )

async def receive_daily_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    is_member = await check_channel_membership(user.id, context)
    if not is_member:
        await update.message.reply_text(
            "⚠️ شما عضو همه کانال‌های رسمی ما نیستید.\n"
            "لطفا ابتدا عضو همه کانال‌ها شوید و سپس دوباره تلاش کنید."
        )
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("SELECT last_daily_receive FROM users WHERE user_id=?", (user.id,)) as cursor:
            row = await cursor.fetchone()

        last_daily_receive = row[0] if row else None
        now = datetime.utcnow()

        if last_daily_receive:
            try:
                last_dt = datetime.strptime(last_daily_receive, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                last_dt = datetime.strptime(last_daily_receive, "%Y-%m-%d %H:%M:%S")
            if (now - last_dt) < timedelta(hours=24):
                remain = timedelta(hours=24) - (now - last_dt)
                h, m = divmod(remain.seconds // 60, 60)
                await update.message.reply_text(
                    f"⏰ شما فقط هر ۲۴ ساعت یک بار می‌توانید کانفیگ روزانه دریافت کنید.\n"
                    f"زمان باقی‌مانده تا دریافت بعدی: {h} ساعت و {m} دقیقه."
                )
                return

        user_states[user.id] = {"waiting_for": "daily_code"}
        await update.message.reply_text(
            "🔑 لطفا کد ۵ رقمی کانفیگ روزانه را وارد کنید:",
            reply_markup=back_keyboard(),
        )

async def validate_daily_code(update: Update, context: ContextTypes.DEFAULT_TYPE, code: str):
    user = update.effective_user
    # بررسی دکمه بازگشت در ابتدای تابع
    if code == "🔙 بازگشت":
        user_states.pop(user.id, None)
        await update.message.reply_text(
            "🔙 بازگشت به منوی اصلی.",
            reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        )
        return

    now = datetime.utcnow()

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("""
            SELECT c.name, c.link, c.code, IFNULL(u.used, 0) as used
            FROM configs c
            LEFT JOIN usage u ON c.name = u.config_name
            WHERE c.type = 'daily'
            ORDER BY c.rowid DESC
            LIMIT 1
            """) as cursor:
            config = await cursor.fetchone()

        if not config:
            await update.message.reply_text(
                "😔 متاسفانه در حال حاضر کانفیگ روزانه فعالی وجود ندارد. لطفا بعدا تلاش کنید.",
                reply_markup=main_keyboard(is_admin=is_admin(user.id)),
            )
            user_states.pop(user.id, None)
            return

        name, link, config_code, used = config

        if code != config_code:
            await update.message.reply_text(
                "❌ کد وارد شده اشتباه است. لطفا دوباره تلاش کنید:",
                reply_markup=back_keyboard(),
            )
            return

        if used >= 10:
            await update.message.reply_text(
                "⚠️ ظرفیت این کانفیگ روزانه پر شده است. لطفا بعدا تلاش کنید.",
                reply_markup=main_keyboard(is_admin=is_admin(user.id)),
            )
            user_states.pop(user.id, None)
            return

        await db.execute(
            "INSERT OR IGNORE INTO usage(config_name, used) VALUES (?, 0)",
            (name,),
        )
        await db.execute(
            "UPDATE usage SET used = used + 1 WHERE config_name = ?",
            (name,),
        )
        await db.execute(
            "UPDATE users SET last_daily_receive = ? WHERE user_id = ?",
            (now.strftime("%Y-%m-%d %H:%M:%S.%f"), user.id),
        )
        await db.commit()

    text = f"""
*کانفیگ روزانه ☀️*
اطلاعات کانفیگ: تک کاربره - حجم مجاز به استفاده یک گیگ

⚠️شرایط استفاده از کانفیگ: تنها به صورت تک نفره مجاز به استفاده از کانفیگ هستید، اگر خواستید برای کسی ارسالش کنید، باید کانفیگ رو برنامه پاک کنید. 
اگر خواستید برای کسی ارسال کنید، فقط از ایتا استفاده کنید و وقتی دوستتون سین کرد و کانفیگ رو ذخیره کرد، سریعاً پیام رو پاک کنید. اگر در صورت بروز باگ تونستید بیش‌تر از یک گیگ استفاده کنید، اخلاقیات رو رعایت کنید و به حجمی که دارید قانع باشید، زیرا علاوه بر شما، ۹ نفر دیگه به اون کانفیگ وصلن. پس حواستون به حق‌الناس باشه.
{link}


👤 Provider: @amiraly001, @arshiashi

[آموزش استفاده از کانفیگ‌ها](https://t.me/arshiashi/3968)
ظرفیت شما برای دریافت کانفیگ روزانه پر شد. برای دریافت مجدد؛ فردا به ربات سر بزنید.
Our channel: @Arshiashi
"""

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    user_states.pop(user.id, None)

async def receive_emergency_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    is_member = await check_channel_membership(user.id, context)
    if not is_member:
        await update.message.reply_text(
            "⚠️ شما عضو همه کانال‌های رسمی ما نیستید.\n"
            "لطفا ابتدا عضو همه کانال‌ها شوید و سپس دوباره تلاش کنید."
        )
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("""
            SELECT name, link
            FROM configs
            WHERE type = 'emergency'
            ORDER BY rowid DESC
            LIMIT 1
            """) as cursor:
            config = await cursor.fetchone()

        if not config:
            await update.message.reply_text(
                "😔 متاسفانه در حال حاضر کانفیگ اضطراری وجود ندارد."
            )
            return

        name, link = config

    from telegram.helpers import escape_markdown

    text = f"""
*کانفیگ اضطراری 🚨*

⚠️ شرایط استفاده از کانفیگ: در صورتی که خیلی دیگه کارتون گیر بود و هیچ کانفیگی دم دستتون نبود، این رو تست کنید. توجه کنید به هیییییییییچ عنوان با این کانفیگ دانلود نکنید و فقط باهاش تکست بدید.
شانس وصل شدنتون ۵۰/۵۰ پس اگه وصل نشدید و همچنان کارتون گیر بود، می‌تونید از فروشندهٔ بات، کانفیگ خریداری کنید. پس اگر وصل نشد، پیشاپیش عذرخواهی می‌کنم.
{link}


👤 Provider: @amiraly001, @arshiashi

[آموزش استفاده از کانفیگ‌ها](https://t.me/arshiashi/3968)
ظرفیت شما برای دریافت کانفیگ روزانه پر شد. برای دریافت مجدد؛ فردا به ربات سر بزنید.
Our channel: @Arshiashi
"""

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )
    user_states.pop(user.id, None)

async def receive_emergency_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    is_member = await check_channel_membership(user.id, context)
    if not is_member:
        await update.message.reply_text(
            "⚠️ شما عضو همه کانال‌های رسمی ما نیستید.\n"
            "لطفا ابتدا عضو همه کانال‌ها شوید و سپس دوباره تلاش کنید."
        )
        return

    async with aiosqlite.connect(DB_FILE) as db:
        async with db.execute("""
            SELECT name, link
            FROM configs
            WHERE type = 'emergency'
            ORDER BY rowid DESC
            LIMIT 1
            """) as cursor:
            config = await cursor.fetchone()

        if not config:
            await update.message.reply_text(
                "😔 متاسفانه در حال حاضر کانفیگ اضطراری وجود ندارد."
            )
            return

        name, link = config

    from telegram.helpers import escape_markdown

    text = f"""
*کانفیگ اضطراری 🚨*

⚠️ شرایط استفاده از کانفیگ: در صورتی که خیلی دیگه کارتون گیر بود و هیچ کانفیگی دم دستتون نبود، این رو تست کنید. توجه کنید به هیییییییییچ عنوان با این کانفیگ دانلود نکنید و فقط باهاش تکست بدید.
شانس وصل شدنتون ۵۰/۵۰ پس اگه وصل نشدید و همچنان کارتون گیر بود، می‌تونید از فروشندهٔ بات، کانفیگ خریداری کنید. پس اگر وصل نشد، پیشاپیش عذرخواهی می‌کنم.
{link}


[آموزش استفاده از کانفیگ‌ها](https://t.me/arshiashi/3968)
نکته مهم: اگر صاحب چنل هستید، تحت هیچ شرایطی اجازهٔ شیر کردن این کانفیگ‌هارو ندارید. این کانفیگ فقط برای اتصال مردمه و شما با شیر کردنش باعث می‌شید خرابی پیش بیاد و مردم نتونن وصل بشن. ما که به هیچ عنوان راضی نیستیم. پس اگر “مردم” براتون مهم‌ان شیر نکنید.
"""

    await update.message.reply_text(
        text,
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        parse_mode="Markdown",
        disable_web_page_preview=True,
    )

async def buy_custom_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = """
*خرید کانفیگ اختصاصی 🛒*

برای سفارش کانفیگ اختصاصی با مشخصات دلخواه خودتون، لطفا از طریق پیام به آیدی زیر اقدام کنید:

@Amiraly7

⚠️ نکتهٔ مهم:
• مسئولیت خرید، بین خودتون و فروشنده‌ست. منِ عرشیا نظارتی روی این بخش ندارم چون فروشنده نیستم. اما می‌تونید خریدتون رو امن انجام بدید و رضایت‌ مشتری‌هارو @TrustAmi این‌جا ببینید.
"""
    await update.message.reply_text(
        text,
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        parse_mode="Markdown",
    )

@admin_only
async def admin_add_config_process(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    user = update.effective_user
    state = admin_states.get(user.id, {"waiting_for": None, "data": {}})

    if text == "🔙 بازگشت":
        admin_states.pop(user.id, None)
        await update.message.reply_text(
            "🔙 بازگشت به منوی اصلی.",
            reply_markup=main_keyboard(is_admin=True),
        )
        return

    waiting_for = state["waiting_for"]
    new_config_temp = state["data"]

    async with aiosqlite.connect(DB_FILE) as conn:
        if waiting_for == "type":
            if text not in ["Daily", "Emergency"]:
                await update.message.reply_text(
                    "⚠️ لطفا نوع کانفیگ را با استفاده از دکمه‌ها انتخاب کنید.",
                    reply_markup=config_type_keyboard(),
                )
                return
            new_config_temp["type"] = text.lower()
            waiting_for = "link"
            await update.message.reply_text(
                "🔗 لینک کانفیگ را وارد کنید:",
                reply_markup=back_keyboard(),
            )
        elif waiting_for == "link":
            new_config_temp["link"] = text.strip()
            new_config_temp["name"] = f"config_{int(datetime.utcnow().timestamp())}"
            code = str(random.randint(10000, 99999)) if new_config_temp["type"] == "daily" else None

            try:
                await conn.execute(
                    "INSERT INTO configs(name, type, link, code) VALUES (?, ?, ?, ?)",
                    (
                        new_config_temp["name"],
                        new_config_temp["type"],
                        new_config_temp["link"],
                        code,
                    ),
                )
                if new_config_temp["type"] == "daily":
                    await conn.execute(
                        "INSERT OR IGNORE INTO usage(config_name, used) VALUES (?, 0)",
                        (new_config_temp["name"],),
                    )
                await conn.commit()
                response_text = "✅ کانفیگ جدید با موفقیت اضافه شد."
                if code:
                    response_text += f"\n🔑 کد کانفیگ روزانه: {code}"
                await update.message.reply_text(
                    response_text,
                    reply_markup=main_keyboard(is_admin=True),
                )
            except aiosqlite.IntegrityError:
                await update.message.reply_text(
                    "❌ خطا در افزودن کانفیگ. لطفا دوباره تلاش کنید.",
                    reply_markup=back_keyboard(),
                )
                return
            finally:
                waiting_for = None
                new_config_temp = {}
        else:
            waiting_for = "type"
            new_config_temp = {}
            await update.message.reply_text(
                "➕ نوع کانفیگ را انتخاب کنید:",
                reply_markup=config_type_keyboard(),
            )

        admin_states[user.id] = {"waiting_for": waiting_for, "data": new_config_temp}

async def guide(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    guide_text = (
        "📘 **راهنمای استفاده از ربات** 📘\n\n"
        "برای شما سه گزینه در دسترس است:\n\n"
        "1️⃣ **کانفیگ اضطراری**: این کانفیگ عمومی است و هیچ محدودیتی برای کاربران ندارد. با این حال، ممکن است برخی کاربران نتوانند متصل شوند.\n\n"
        "2️⃣ **کانفیگ روزانه**: این کانفیگ خصوصی است و دارای محدودیت‌های زیر می‌باشد:\n"
        "   • هر کانفیگ ظرفیت ۱۰ کاربر دارد.\n"
        "   • برای دریافت، نیاز به کد ۵ رقمی دارید که توسط ادمین ارائه می‌شود.\n"
        "   • هر کاربر می‌تواند هر ۲۴ ساعت یک کانفیگ دریافت کند.\n\n"
        "3️⃣ **کانفیگ اختصاصی**: اگر فکر می‌کنید به کانفیگ دائمی نیاز دارید، می‌توانید با واحد پشتیبانی ما تماس بگیرید و کانفیگ خریداری کنید. (مسئولیت بین شما و پشتیبان است و من، عرشیا، نمی‌توانم این موضوع را نظارت کنم زیرا فروشنده نیستم.)\n\n"
        "⚠️ **نکته مهم**: تحت هیچ شرایطی کانفیگ‌های این ربات را عمومی نکنید یا به اشتراک نگذارید. فقط در صورت لزوم متصل شوید یا با دوستان خود به مقدار کم به اشتراک بگذارید.\n"
        "امیدوارم اخلاق را رعایت کنید و به ما در ادامه این پروژه کمک کنید."
    )
    await update.message.reply_text(
        guide_text,
        parse_mode="Markdown",
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
    )

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not update.message or not update.message.text:
        return

    text = update.message.text

    if is_admin(user.id) and text == "➕ افزودن کانفیگ جدید":
        admin_states[user.id] = {"waiting_for": "type", "data": {}}
        await update.message.reply_text(
            "➕ نوع کانفیگ را انتخاب کنید:",
            reply_markup=config_type_keyboard(),
        )
        return

    if text == "📩 دریافت کانفیگ روزانه":
        await receive_daily_config(update, context)
        return

    if text == "🚨 دریافت کانفیگ اضطراری":
        await receive_emergency_config(update, context)
        return

    if text == "🛒 خرید کانفیگ اختصاصی":
        await buy_custom_config(update, context)
        return

    if text == "ℹ️ راهنما":
        await guide(update, context)
        return

    if is_admin(user.id) and user.id in admin_states:
        await admin_add_config_process(update, context, text)
        return

    if user.id in user_states and user_states[user.id]["waiting_for"] == "daily_code":
        await validate_daily_code(update, context, text)
        return

    if text == "🔙 بازگشت":
        admin_states.pop(user.id, None)
        user_states.pop(user.id, None)
        await update.message.reply_text(
            "🔙 بازگشت به منوی اصلی.",
            reply_markup=main_keyboard(is_admin=is_admin(user.id)),
        )
        return

    await update.message.reply_text(
        "⚠️ دستور نامشخص است. لطفا از دکمه‌های موجود استفاده کنید.",
        reply_markup=main_keyboard(is_admin=is_admin(user.id)),
    )

async def main():
    await init_db()
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), message_handler))

    await application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())


