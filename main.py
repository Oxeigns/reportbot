import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
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
    
    text = f"""🔥 **STARTLOVE v3.0** ✅

📊 **STATS:**
• `{stats['active']}` Active ✅
• `{stats['pending']}` Pending ⏳
• `{stats['failed']}` Failed ❌
• `{stats['total']}` Total 📈

👤 **You:** {'🔥 ADMIN' if is_admin else '👤 User'}
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

✅ **ACTIVE:** `{stats['active']}`
⏳ **PENDING:** `{stats['pending']}`
❌ **FAILED:** `{stats['failed']}`
📈 **TOTAL:** `{stats['total']}`
👥 **SUDOS:** `{stats['sudo']}`
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^validate_all$"))
async def validate_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    if not reporter.has_api_credentials():
        await callback.message.edit_text(
            "❌ **MISSING API_ID/API_HASH**\n\n"
            "Set `API_ID` and `API_HASH` in config vars before validating."
        )
        return
    await callback.message.edit_text("🔄 **VALIDATING... (30s)**")
    
    results = await reporter.validate_all_sessions()
    stats = await db.get_stats()
    
    emoji = "✅" if stats['active'] > 0 else "⚠️"
    keyboard = main_keyboard(await is_authorized(callback.from_user.id))
    
    text = f"""✅ **VALIDATION DONE!**

{emoji} **ACTIVE:** `{results['active']}` ✅
❌ **FAILED:** `{results['failed']}` ❌
📊 **CHECKED:** `{results['total']}`

**READY TO REPORT!** 🔥
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^add_session$"))
async def add_session_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    app.user_states[callback.from_user.id] = {"step": "add_session"}
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]])
    await callback.message.edit_text(
        "📝 **PASTE SESSIONS:**\n\n"
        "• **One per line**\n"
        "• **Pyrogram v2** (`1BV...`)\n\n"
        "`1BVABC...`\n`1BVDEF...`\n`1BVXYZ...`\n\n"
        "**Send now!**",
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^start_report$"))
async def start_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    stats = await db.get_stats()
    
    if stats['active'] == 0:
        await callback.message.edit_text(
            "❌ **0 ACTIVE SESSIONS!**\n\n"
            "**1️⃣ ADD SESSION**\n**2️⃣ VALIDATE ALL**",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD", callback_data="add_session")],
                [InlineKeyboardButton("🔄 VALIDATE", callback_data="validate_all")],
                [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
            ])
        )
        return
    
    app.user_states[callback.from_user.id] = {"step": "target_chat"}
    await callback.message.edit_text(
        f"✅ **{stats['active']} READY!** 🔥\n\n"
        "🔗 **TARGET CHAT:**\n\n"
        "`@username`\n`t.me/username`",
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
        
        for i, session in enumerate(lines):
            ok, msg = await db.add_session(session, f"sess_{i+1}")
            if ok:
                success_count += 1
        
        stats = await db.get_stats()
        keyboard = main_keyboard(True)
        
        await message.reply_text(
            f"✅ **{success_count}/{len(lines)} ADDED!**\n\n"
            f"📊 `{stats['active']}` Active | `{stats['total']}` Total\n\n"
            "**🔄 VALIDATE NOW** 👇",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        del app.user_states[user_id]

    elif state["step"] == "target_chat":
        if not reporter.has_api_credentials():
            await message.reply_text(
                "❌ **MISSING API_ID/API_HASH**\n\n"
                "Set `API_ID` and `API_HASH` in config vars before reporting."
            )
            del app.user_states[user_id]
            return
        chat_id = get_chat_id(text)
        app.user_states[user_id] = {"step": "reporting", "target": chat_id}
        
        await reporter.load_active_clients()
        joined = await reporter.join_target_chat(chat_id)
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🚀 REPORT NOW", callback_data=f"mass_report_{chat_id}")],
            [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
        ])
        
        await message.reply_text(
            f"✅ **JOINED:** {joined}/{len(reporter.active_clients)}\n\n"
            f"🎯 **{chat_id}** ✅\n\n"
            "**Click REPORT NOW!** 🔥",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )

def get_chat_id(link: str) -> str:
    link = link.split("?")[0].strip()
    if "/joinchat/" in link:
        return link.split("/joinchat/")[1]
    if "t.me/" in link:
        parts = link.split("t.me/")[1].split("/")
        username = parts[0].strip()
        return f"@{username}" if not username.startswith("@") else username
    return link.lstrip("@")

@app.on_callback_query(filters.regex("^mass_report_"))
async def mass_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    chat_id = callback.data.split("_", 2)[2]
    
    await callback.message.edit_text("🔥 **REPORTING...**")
    results = await reporter.mass_report_chat(chat_id)
    
    keyboard = main_keyboard(await is_authorized(callback.from_user.id))
    
    text = f"""🎉 **REPORT FINISHED!**

✅ **SUCCESS:** `{results['success']}`
❌ **FAILED:** `{results['failed']}`
📊 **TOTAL:** `{results['total']}`

🎯 **{chat_id}**
"""
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^(home|help|manage_sudos)$"))
async def other_callbacks(client, callback: CallbackQuery):
    await safe_answer(callback)
    await callback.answer("🔥 Coming soon!", show_alert=True)

if __name__ == "__main__":
    print("🚀 STARTLOVE v3.0 - ULTIMATE ✅")
    app.run()
