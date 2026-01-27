import re
import asyncio
import logging
from pyrogram import Client, filters
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, OWNER_ID, SUDO_USERS, API_ID, API_HASH
from database import db
from report import MassReporter

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Client("mass_report_bot", bot_token=BOT_TOKEN, api_id=API_ID, api_hash=API_HASH)
app.user_states = {}
app.report_desc = ""

async def is_authorized(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in SUDO_USERS or await db.is_sudo(user_id)

def get_chat_id(link: str) -> str:
    if link.startswith("https://t.me/"):
        link = link.split("https://t.me/")[1]
    return link.lstrip("@").split("?")[0].rstrip("/")

def is_chat_link(link: str) -> bool:
    return bool(re.match(r"^(?:https?://)?t\.me/|^@", link, re.IGNORECASE))

def is_message_link(link: str) -> bool:
    if not re.match(r"^(?:https?://)?t\.me/", link, re.IGNORECASE):
        return False
    return bool(re.search(r"/\d+$", link))

async def safe_answer(callback):
    try:
        await callback.answer()
    except QueryIdInvalid:
        pass

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    user_id = message.from_user.id
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 START REPORT", callback_data="report")]])
    
    if await is_authorized(user_id):
        keyboard.inline_keyboard.extend([
            [InlineKeyboardButton("➕ ADD SUDO", callback_data="add_sudo"), InlineKeyboardButton("➖ RM SUDO", callback_data="rm_sudo")],
            [InlineKeyboardButton("📊 STATS", callback_data="stats")]
        ])
    
    await message.reply_text("🚨 **MASS REPORT BOT** ✅", reply_markup=keyboard)

@app.on_message(filters.private & ~filters.command("start"))
async def handle_text(client, message):
    user_id = message.from_user.id
    if not await is_authorized(user_id):
        return
    
    state = app.user_states.get(user_id)
    if not state:
        return
    
    text = message.text.strip()
    step = state.get("step")
    
    try:
        if step == "sessions":
            lines = [line.strip() for line in text.split('\n') if line.strip()]
            for i, session in enumerate(lines):
                await db.add_session(session, f"sess_{i+1}")
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ VALIDATE", callback_data="validate")],
                [InlineKeyboardButton("🔙 BACK", callback_data="back")]
            ])
            await message.reply_text(f"✅ **Saved {len(lines)} sessions**", reply_markup=keyboard)
        
        elif step == "chat_link" and is_chat_link(text):
            state["chat"] = text
            state["step"] = "target_link"
            
            reporter = MassReporter()
            await reporter.load_validated_sessions()
            
            if not reporter.active_clients:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ VALIDATE FIRST", callback_data="validate")],
                    [InlineKeyboardButton("🔙 BACK", callback_data="back")]
                ])
                await message.reply_text("❌ **No active sessions!**", reply_markup=keyboard)
                return
            
            joined = await reporter.join_chat(text)
            await message.reply_text(f"✅ **Joined: {joined}** clients\n\n🎯 **Send target MSG link:**")
        
        elif step == "target_link" and is_message_link(text):
            chat_id = get_chat_id(state["chat"])
            target_id = get_chat_id(text)
            
            if chat_id != target_id:
                await message.reply_text("❌ **Same chat ka link!**")
                return
            
            state["target"] = target_id
            state["step"] = "reason"
            
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("📧 SPAM", callback_data=f"spam:{target_id}")],
                [InlineKeyboardButton("🔪 VIOLENCE", callback_data=f"vio:{target_id}")],
                [InlineKeyboardButton("🔞 PORN", callback_data=f"porn:{target_id}")],
                [InlineKeyboardButton("🔙 BACK", callback_data="back")]
            ])
            await message.reply_text(f"✅ **Target: {target_id}**\n**Choose reason:**", reply_markup=keyboard)
        
        elif step == "desc":
            app.report_desc = text
            state["step"] = "count"
            await message.reply_text(f"📝 **Desc:** `{text[:30]}...`\n\n**Reports per session:**")
        
        elif step == "count" and text.isdigit():
            count = int(text)
            reporter = MassReporter()
            await reporter.load_validated_sessions()
            
            status = await message.reply_text("🚀 **Reporting...**")
            success, failed = await reporter.mass_report(
                state["target"], state["reason"], app.report_desc, count
            )
            
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MENU", callback_data="back")]])
            await status.edit_text(
                f"✅ **DONE!**\n🟢 Success: {success}\n🔴 Failed: {failed}\n📊 Total: {success+failed}",
                reply_markup=keyboard
            )
            app.user_states.pop(user_id)
    
    except Exception as e:
        logger.error(f"Handle text error: {e}")
        await message.reply_text("❌ Something went wrong!")

@app.on_callback_query(filters.regex("report"))
async def report_menu(client, callback):
    await safe_answer(callback)
    if not await is_authorized(callback.from_user.id):
        await callback.answer("❌ Unauthorized!", show_alert=True)
        return
    
    total = await db.get_total_session_count()
    active = await db.get_active_session_count()
    
    if total == 0:
        app.user_states[callback.from_user.id] = {"step": "sessions"}
        await callback.message.edit_text(
            "📝 **Send Pyrogram sessions** (one per line):\n\n"
            "`BQC...`\n`BQC...`",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]]),
            parse_mode="markdown"
        )
        return
    
    if active == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Validate", callback_data="validate")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        await callback.message.edit_text("❌ No active sessions!", reply_markup=keyboard)
        return
    
    app.user_states[callback.from_user.id] = {"step": "chat_link"}
    await callback.message.edit_text(
        "🔗 **Send chat link:**\n\n`@username` or `t.me/username`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
    )

@app.on_callback_query(filters.regex(r"(spam|vio|porn):(.+)"))
async def reason_cb(client, callback):
    await safe_answer(callback)
    reasons = {"spam": 1, "vio": 3, "porn": 8}
    
    _, target = callback.data.split(":", 1)
    reason = reasons[callback.data.split(":")[0]]
    
    state = app.user_states[callback.from_user.id]
    state["reason"] = reason
    state["step"] = "desc"
    
    await callback.message.edit_text(
        f"⚠️ **Reason selected**\n🎯 **Target:** `{target}`\n\n"
        "**Send description:**"
    )

@app.on_callback_query(filters.regex("validate"))
async def validate_cb(client, callback):
    await safe_answer(callback)
    await callback.message.edit_text("⏳ **Validating...**")
    
    reporter = MassReporter()
    count = await reporter.load_sessions()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Report", callback_data="report")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    await callback.message.edit_text(f"✅ **{count} active sessions**", reply_markup=keyboard)

@app.on_callback_query(filters.regex("back"))
async def back_cb(client, callback):
    await safe_answer(callback)
    app.user_states.pop(callback.from_user.id, None)
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 Report", callback_data="report")]])
    if await is_authorized(callback.from_user.id):
        keyboard.inline_keyboard.extend([
            [InlineKeyboardButton("➕ Sudo", callback_data="add_sudo"), InlineKeyboardButton("➖ Sudo", callback_data="rm_sudo")],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ])
    
    await callback.message.edit_text("🚨 **Mass Report Bot**", reply_markup=keyboard)

if __name__ == "__main__":
    print("🚀 Bot starting...")
    app.run()
