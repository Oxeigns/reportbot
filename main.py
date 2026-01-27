import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode, ChatType
from config import BOT_TOKEN, OWNER_ID
from database import db
from report import reporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("startlove_bot", bot_token=BOT_TOKEN)
app.user_states = {}

async def is_authorized(user_id: int) -> bool:
    return user_id == OWNER_ID or await db.is_sudo(user_id)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except:
        pass

def main_keyboard(is_admin: bool = False):
    keyboard = [
        [InlineKeyboardButton("🚀 START REPORT", callback_data="start_report")],
        [InlineKeyboardButton("📊 STATS", callback_data="stats")]
    ]
    if is_admin:
        keyboard.extend([
            [InlineKeyboardButton("➕ ADD SESSION", callback_data="add_session")],
            [InlineKeyboardButton("🔄 VALIDATE ALL", callback_data="validate_all")],
            [InlineKeyboardButton("👥 SUDOS", callback_data="manage_sudos")]
        ])
    keyboard.append([InlineKeyboardButton("ℹ️ HELP", callback_data="help")])
    return InlineKeyboardMarkup(keyboard)

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    is_admin = await is_authorized(message.from_user.id)
    stats = await db.get_stats()
    
    text = f"""🔥 **STARTLOVE MASS REPORTER** v2.0 ✅

📊 **STATS:**
• Total Sessions: `{stats['total']}`
• Active: `{stats['active']}` ✅
• Pending: `{stats['pending']}`
• Failed: `{stats['failed']}` ❌

👤 **Status:** {'🔥 ADMIN' if is_admin else '👤 User'}
"""
    
    await message.reply_text(text, reply_markup=main_keyboard(is_admin), parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    stats = await db.get_stats()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 REFRESH", callback_data="stats")],
        [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
    ])
    
    text = f"""📊 **LIVE STATS** 🔥

🔥 **ACTIVE:** `{stats['active']}`
⏳ **PENDING:** `{stats['pending']}`
❌ **FAILED:** `{stats['failed']}`
📈 **TOTAL:** `{stats['total']}`
👥 **SUDOS:** `{stats['sudo']}`
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^validate_all$"))
async def validate_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    await callback.message.edit_text("🔄 **VALIDATING SESSIONS...**")
    
    results = await reporter.validate_all_sessions()
    stats = await db.get_stats()
    
    keyboard = main_keyboard(await is_authorized(callback.from_user.id))
    
    text = f"""✅ **VALIDATION COMPLETE!**

✅ **ACTIVE:** `{results['active']}`
❌ **FAILED:** `{results['failed']}`
📊 **TOTAL CHECKED:** `{results['total']}`

**CURRENT STATS:**
• Active: `{stats['active']}` ✅
• Failed: `{stats['failed']}` ❌
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^add_session$"))
async def add_session_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    app.user_states[callback.from_user.id] = {"step": "add_session"}
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]])
    await callback.message.edit_text(
        "📝 **SEND SESSION STRINGS:**\n\n"
        "• **One per line**\n"
        "• **Pyrogram v2 format** (starts with `1` or `BV`)\n\n"
        "`1BV...`\n`1BV...`\n`1BV...`",
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^start_report$"))
async def start_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    stats = await db.get_stats()
    
    if stats['active'] == 0:
        await callback.message.edit_text(
            "❌ **NO ACTIVE SESSIONS!**\n\n"
            "🔄 **First:** ADD → VALIDATE",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD SESSION", callback_data="add_session")],
                [InlineKeyboardButton("🔄 VALIDATE", callback_data="validate_all")],
                [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
            ])
        )
        return
    
    app.user_states[callback.from_user.id] = {"step": "target_chat"}
    await callback.message.edit_text(
        f"✅ **{stats['active']} ACTIVE SESSIONS READY!** 🔥\n\n"
        "🔗 **SEND TARGET CHAT:**\n\n"
        "`@channelname`\n`https://t.me/channelname`",
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_message(filters.private & filters.text & ~filters.command("start"))
async def handle_user_input(client, message):
    user_id = message.from_user.id
    state = app.user_states.get(user_id)
    if not state or not await is_authorized(user_id):
        return
    
    text = message.text.strip()
    
    if state["step"] == "add_session":
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        success_count = 0
        
        for session in lines:
            ok, msg = await db.add_session(session)
            if ok:
                success_count += 1
        
        stats = await db.get_stats()
        keyboard = main_keyboard(True)
        
        await message.reply_text(
            f"✅ **Added {success_count}/{len(lines)} sessions!**\n\n"
            f"📊 **Active:** `{stats['active']}` | **Total:** `{stats['total']}`\n\n"
            "**🔄 Click VALIDATE ALL**",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        del app.user_states[user_id]
    
    elif state["step"] == "target_chat":
        chat_id = get_chat_id(text)
        app.user_states[user_id] = {"step": "reporting", "target": chat_id}
        
        await reporter.load_active_clients()
        joined = await reporter.join_target_chat(chat_id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 MASS REPORT", callback_data=f"mass_report_{chat_id}")],
            [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
        ])
        
        await message.reply_text(
            f"✅ **JOINED:** {joined}/{len(reporter.active_clients)}\n\n"
            f"🎯 **Target:** `{chat_id}`\n\n"
            "**Ready to MASS REPORT!** 🔥",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )

def get_chat_id(link: str) -> str:
    link = link.split("?")[0]
    if "t.me/" in link:
        parts = link.split("t.me/")[1].split("/")
        return f"@{parts[0]}" if parts[0].startswith("@") else parts[0]
    return link.lstrip("@")

@app.on_callback_query(filters.regex("^mass_report_"))
async def mass_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    chat_id = callback.data.split("_", 2)[2]
    
    await callback.message.edit_text("🔥 **MASS REPORTING...**")
    results = await reporter.mass_report_chat(chat_id)
    
    keyboard = main_keyboard(await is_authorized(callback.from_user.id))
    
    text = f"""✅ **REPORT COMPLETE!** 🎉

✅ **SUCCESS:** `{results['success']}`
❌ **FAILED:** `{results['failed']}`
📊 **TOTAL:** `{results['total']}`

🎯 **Target:** `{chat_id}`
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^(home|help)$"))
async def home_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    is_admin = await is_authorized(callback.from_user.id)
    await callback.message.edit_text(
        "🏠 **MAIN MENU**", reply_markup=main_keyboard(is_admin),
        parse_mode=ParseMode.MARKDOWN
    )

if __name__ == "__main__":
    print("🚀 STARTLOVE ULTIMATE BOT LAUNCHING...")
    app.run()
