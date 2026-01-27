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

async def is_authorized(user_id: int) -> bool:
    """Check if user is authorized"""
    return user_id == OWNER_ID or user_id in SUDO_USERS or await db.is_sudo(user_id)

def get_chat_id(link: str) -> str:
    """Extract chat ID from link"""
    if link.startswith("https://t.me/"):
        link = link.split("https://t.me/")[1]
    return link.lstrip("@").split("?")[0].rstrip("/")

def is_chat_link(link: str) -> bool:
    """Validate chat link format"""
    return bool(re.match(r"^(?:https?://)?t\.me/|^@", link, re.IGNORECASE))

def is_message_link(link: str) -> bool:
    """Validate message link format"""
    if not re.match(r"^(?:https?://)?t\.me/", link, re.IGNORECASE):
        return False
    return bool(re.search(r"/\d+$", link))

async def safe_answer(callback):
    """Safely answer callback query"""
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
            [
                InlineKeyboardButton("➕ ADD SUDO", callback_data="add_sudo"),
                InlineKeyboardButton("➖ REMOVE SUDO", callback_data="rm_sudo")
            ],
            [InlineKeyboardButton("📊 STATS", callback_data="stats")]
        ])
    
    await message.reply_text(
        "🚨 **MASS REPORT BOT** ✅\n\n"
        "Click **START REPORT** to begin!",
        reply_markup=keyboard
    )

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
    
    if step == "sessions":
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        for i, session in enumerate(lines):
            await db.add_session(session, f"sess_{i+1}")
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ VALIDATE SESSIONS", callback_data="validate")],
            [InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]
        ])
        await message.reply_text(
            f"✅ **Saved {len(lines)} sessions successfully!**\n\n"
            "Click **VALIDATE SESSIONS**",
            reply_markup=keyboard
        )
    
    elif step == "chat_link" and is_chat_link(text):
        state["chat"] = text
        state["step"] = "target_link"
        
        reporter = MassReporter()
        await reporter.load_validated_sessions()
        
        if not reporter.active_clients:
            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ VALIDATE SESSIONS", callback_data="validate")],
                [InlineKeyboardButton("🔙 BACK", callback_data="back")]
            ])
            await message.reply_text(
                "❌ **No active sessions found!**\nValidate first.",
                reply_markup=keyboard
            )
            return
        
        joined = await reporter.join_chat(text)
        state["joined"] = joined
        
        await message.reply_text(
            f"✅ **Chat Joined Successfully!**\n"
            f"🟢 **{joined}/{len(reporter.active_clients)} clients joined**\n\n"
            f"🎯 **Send TARGET MESSAGE LINK:**\n"
            f"`https://t.me/channel/123`"
        )
    
    elif step == "target_link" and is_message_link(text):
        chat_id = get_chat_id(state["chat"])
        target_id = get_chat_id(text)
        
        if chat_id != target_id:
            await message.reply_text("❌ **Target must be from SAME CHAT!**")
            return
        
        state["target"] = target_id
        state["step"] = "reason"
        
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📧 SPAM", callback_data=f"spam:{target_id}")],
            [InlineKeyboardButton("🔪 VIOLENCE", callback_data=f"vio:{target_id}")],
            [InlineKeyboardButton("🔞 PORN", callback_data=f"porn:{target_id}")],
            [InlineKeyboardButton("🔙 BACK", callback_data="back")]
        ])
        await message.reply_text(
            f"✅ **Target Confirmed: `{target_id}`**\n\n"
            "**Choose Report Reason:**",
            reply_markup=keyboard
        )
    
    elif step == "desc":
        app.report_desc = text[:500]  # Limit length
        state["step"] = "count"
        await message.reply_text(
            f"📝 **Description:** `{text[:50]}...`\n\n"
            "**Enter reports PER SESSION:**\n"
            "`5` `10` `20`"
        )
    
    elif step == "count" and text.isdigit():
        count = int(text)
        if count > 50:  # Limit
            await message.reply_text("❌ **Max 50 reports per session!**")
            return
        
        reporter = MassReporter()
        await reporter.load_validated_sessions()
        
        if not reporter.active_clients:
            await message.reply_text("❌ **No active sessions!**")
            return
        
        status_msg = await message.reply_text("🚀 **MASS REPORT STARTED...**")
        
        success, failed = await reporter.mass_report(
            state["target"], 
            state["reason"], 
            app.report_desc, 
            count
        )
        
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]])
        await status_msg.edit_text(
            f"✅ **REPORT COMPLETE!**\n\n"
            f"🟢 **Success:** {success}\n"
            f"🔴 **Failed:** {failed}\n"
            f"📊 **Total Sessions:** {success + failed}\n"
            f"🎯 **Total Reports:** {success * count}\n\n"
            f"**Target:** `{state['target']}`",
            reply_markup=keyboard
        )
        app.user_states.pop(user_id)

@app.on_callback_query(filters.regex("report"))
async def report_menu(client, callback):
    await safe_answer(callback)  # ✅ FIXED: AWAIT ADDED
    if not await is_authorized(callback.from_user.id):
        await callback.answer("❌ **Owner/Sudo Only!**", show_alert=True)
        return
    
    total = await db.get_total_session_count()
    active = await db.get_active_session_count()
    
    if total == 0:
        app.user_states[callback.from_user.id] = {"step": "sessions"}
        await callback.message.edit_text(
            "📝 **ADD PYROGRAM SESSION STRINGS**\n\n"
            "**Send one per line:**\n"
            "```\n"
            "BQC...\n"
            "BQC...\n"
            "```",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]]),
            parse_mode="markdown"
        )
        return
    
    if active == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ VALIDATE SESSIONS", callback_data="validate")],
            [InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]
        ])
        await callback.message.edit_text(
            f"❌ **No ACTIVE sessions!**\n\n"
            f"📊 Total: {total} | Active: {active}",
            reply_markup=keyboard
        )
        return
    
    # Prompt for chat link
    app.user_states[callback.from_user.id] = {"step": "chat_link"}
    await callback.message.edit_text(
        "🔗 **SEND CHAT LINK:**\n\n"
        "**Examples:**\n"
        "`@channelname`\n"
        "`t.me/channelname`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]])
    )

@app.on_callback_query(filters.regex(r"(spam|vio|porn):(.+)"))
async def reason_selected(client, callback):
    await safe_answer(callback)  # ✅ FIXED: AWAIT ADDED
    reasons = {"spam": 1, "vio": 3, "porn": 8}
    
    reason_key, target = callback.data.split(":", 1)
    reason = reasons[reason_key]
    
    state = app.user_states[callback.from_user.id]
    state["reason"] = reason
    state["step"] = "desc"
    
    await callback.message.edit_text(  # ✅ FIXED: AWAIT ADDED
        f"⚠️ **Reason:** {reason_key.upper()}\n"
        f"🎯 **Target:** `{target}`\n\n"
        "**Send Report DESCRIPTION:**",
        parse_mode="markdown"
    )

@app.on_callback_query(filters.regex("validate"))
async def validate_cb(client, callback):
    await safe_answer(callback)  # ✅ FIXED: AWAIT ADDED
    await callback.message.edit_text("⏳ **VALIDATING SESSIONS...**")
    
    reporter = MassReporter()
    active_count = await reporter.load_sessions()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 START REPORT", callback_data="report")],
        [InlineKeyboardButton("🔙 MAIN MENU", callback_data="back")]
    ])
    await callback.message.edit_text(
        f"✅ **VALIDATION COMPLETE!**\n\n"
        f"🟢 **Active Sessions:** {active_count}\n"
        f"🔥 **Ready to report!**",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("back"))
async def back_cb(client, callback):
    await safe_answer(callback)  # ✅ FIXED: AWAIT ADDED
    app.user_states.pop(callback.from_user.id, None)
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚨 START REPORT", callback_data="report")]])
    user_id = callback.from_user.id
    
    if await is_authorized(user_id):
        keyboard.inline_keyboard.extend([
            [
                InlineKeyboardButton("➕ ADD SUDO", callback_data="add_sudo"),
                InlineKeyboardButton("➖ REMOVE SUDO", callback_data="rm_sudo")
            ],
            [InlineKeyboardButton("📊 STATS", callback_data="stats")]
        ])
    
    await callback.message.edit_text(  # ✅ FIXED: AWAIT ADDED
        "🚨 **MASS REPORT BOT** ✅\n\n"
        "Click **START REPORT** to begin mass reporting!",
        reply_markup=keyboard
    )

if __name__ == "__main__":
    logger.info("🚀 Starting Mass Report Bot...")
    app.run()
