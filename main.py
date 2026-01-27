import re

from pyrogram import Client, filters, types
from pyrogram.errors.exceptions.bad_request_400 import QueryIdInvalid
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from config import BOT_TOKEN, OWNER_ID, SUDO_USERS, API_ID, API_HASH
from database import db
from report import MassReporter
import asyncio
import logging

logging.basicConfig(level=logging.INFO)

if not API_ID or not API_HASH:
    raise RuntimeError("API_ID and API_HASH must be set for Pyrogram.")

app = Client(
    "mass_report_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)
app.user_states = {}

async def _is_authorized(user_id):
    return user_id == OWNER_ID or user_id in SUDO_USERS or await db.is_sudo(user_id)


def _get_chat_identifier(link):
    if link.startswith("https://t.me/"):
        trimmed = link.split("https://t.me/")[1]
    else:
        trimmed = link
    trimmed = trimmed.lstrip("@")
    trimmed = trimmed.split("?")[0]
    trimmed = trimmed.strip("/")
    return trimmed


def _looks_like_chat_link(link):
    return bool(re.match(r"^(?:https?://)?t\.me/|^@|^\+", link, flags=re.IGNORECASE))


def _looks_like_message_link(link):
    if not re.match(r"^(?:https?://)?t\.me/", link, flags=re.IGNORECASE):
        return False
    return bool(re.search(r"/\d+(?:\?.*)?$", link))


async def _safe_answer_callback(callback):
    try:
        await callback.answer()
    except QueryIdInvalid as exc:
        logging.warning("Callback query expired before answering: %s", exc)


async def _prompt_chat_link(message, user_id):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    app.user_states[user_id] = {"step": "awaiting_chat"}
    await message.edit_text(
        "🔗 **Send Chat Link** (Channel/Group)\n\n"
        "Example: `@channelname` or `https://t.me/channelname`\n"
        "**Private/Public both supported**",
        reply_markup=keyboard
    )

@app.on_message(filters.command("start") & filters.private)
async def start(client, message):
    user_id = message.from_user.id
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Send Report", callback_data="report_start")]
    ])
    
    if user_id == OWNER_ID or user_id in SUDO_USERS:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton("➕ Add Sudo", callback_data="add_sudo"),
            InlineKeyboardButton("➖ Remove Sudo", callback_data="remove_sudo")
        ])
        keyboard.inline_keyboard.append([
            InlineKeyboardButton("📊 Stats", callback_data="stats")
        ])
    
    await message.reply_text(
        "🚨 **Mass Report Bot Active!**\n\n"
        "Click **Send Report** to start mass reporting!",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("report_start"))
async def report_start(client, callback):
    await _safe_answer_callback(callback)
    if not await _is_authorized(callback.from_user.id):
        await callback.answer("❌ Owner/Sudo only.", show_alert=True)
        return
    total_sessions = await db.get_total_session_count()
    active_sessions = await db.get_active_session_count()
    if total_sessions == 0:
        app.user_states[callback.from_user.id] = {"step": "awaiting_sessions"}
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        message_text = (
            "❌ **startlove DB me koi session nahi mila.**\n\n"
            "📝 **Send Session Strings**\n"
            "Send your Pyrogram session strings (one per line)\n"
            "`client1_string`\n"
            "`client2_string`"
        )
        await callback.message.edit_text(
            message_text,
            reply_markup=keyboard
        )
        return
    elif active_sessions > 0:
        await _prompt_chat_link(callback.message, callback.from_user.id)
        return

    await callback.message.edit_text("⏳ **Validating sessions...**")
    reporter = MassReporter()
    active_count = await reporter.load_sessions()
    if active_count == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Validate Sessions", callback_data="validate_sessions")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        await callback.message.edit_text(
            "❌ **No active sessions found.**\n\n"
            "Pehle sessions validate karo.",
            reply_markup=keyboard
        )
        return

    await _prompt_chat_link(callback.message, callback.from_user.id)

@app.on_message(filters.private & ~filters.command("start"))
async def handle_sessions(client, message):
    user_id = message.from_user.id
    if not await _is_authorized(user_id):
        return
    state = app.user_states.get(user_id)
    if not state or state.get("step") != "awaiting_sessions":
        return
    
    text = message.text
    lines = text.strip().split('\n')
    saved_sessions = 0
    
    for i, line in enumerate(lines):
        if line.strip():
            await db.add_session(line.strip(), f"session_{i+1}")
            saved_sessions += 1
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Validate Sessions", callback_data="validate_sessions")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    
    await message.reply_text(
        f"✅ **Saved {saved_sessions} sessions!**\n\n"
        "Click **Validate Sessions** to check them.",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("validate_sessions"))
async def validate_sessions(client, callback):
    await callback.message.edit_text("⏳ **Validating sessions...**")
    
    reporter = MassReporter()
    active_count = await reporter.load_sessions()
    total_sessions = await db.get_total_session_count()
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Start Report", callback_data="start_report")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    
    await callback.message.edit_text(
        f"✅ **Validation Complete!**\n\n"
        f"🟢 Active Sessions: **{active_count}**\n"
        f"🔴 Failed Sessions: **{total_sessions - active_count}**\n\n"
        f"Click **Start Report** to begin!",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("start_report"))
async def start_report(client, callback):
    await _safe_answer_callback(callback)
    if not await _is_authorized(callback.from_user.id):
        await callback.answer("❌ Owner/Sudo only.", show_alert=True)
        return
    active_sessions = await db.get_active_session_count()
    if active_sessions == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Validate Sessions", callback_data="validate_sessions")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        await callback.message.edit_text(
            "❌ **Koi active session nahi mila.**\n\n"
            "Pehle sessions validate karo.",
            reply_markup=keyboard
        )
        return
    await _prompt_chat_link(callback.message, callback.from_user.id)

@app.on_message(filters.private & filters.text)
async def handle_chat_link(client, message):
    user_id = message.from_user.id
    state = app.user_states.get(user_id)
    if not state or state.get("step") != "awaiting_chat":
        return
    if not await _is_authorized(user_id):
        app.user_states.pop(user_id, None)
        await message.reply_text("❌ **Owner/Sudo only.**", parse_mode="markdown")
        return
    chat_link = message.text.strip()
    if not _looks_like_chat_link(chat_link):
        await message.reply_text(
            "❌ **Valid chat link bhejo.**\n\n"
            "Example: `@channelname` ya `https://t.me/channelname`",
            parse_mode="markdown",
            disable_web_page_preview=True
        )
        return
    state["chat_link"] = chat_link

    await message.reply_text("⏳ **Joining chat with active sessions...**")
    reporter = MassReporter()
    active_count = await reporter.load_validated_sessions()
    if active_count == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Validate Sessions", callback_data="validate_sessions")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        await message.reply_text(
            "❌ **No active sessions found.**\n\n"
            "Pehle sessions validate karo.",
            reply_markup=keyboard
        )
        return

    joined = await reporter.join_chat(chat_link)
    state["step"] = "awaiting_target"
    state["joined_summary"] = {
        "joined": joined,
        "total": len(reporter.active_clients)
    }
    await message.reply_text(
        f"✅ **Chat Joined!**\n\n"
        f"🟢 Successfully Joined: **{joined}/{len(reporter.active_clients)}**\n"
        f"📱 Chat: `{chat_link}`\n\n"
        "📝 **Send Target Link** (same chat ka message link)",
        parse_mode="markdown",
        disable_web_page_preview=True
    )

@app.on_message(filters.private & filters.text)
async def handle_target_link(client, message):
    user_id = message.from_user.id
    state = app.user_states.get(user_id)
    if not state or state.get("step") != "awaiting_target":
        return
    if not await _is_authorized(user_id):
        app.user_states.pop(user_id, None)
        await message.reply_text("❌ **Owner/Sudo only.**", parse_mode="markdown")
        return
        
    target_link = message.text.strip()
    if not _looks_like_message_link(target_link):
        await message.reply_text(
            "❌ **Valid message link bhejo.**\n\n"
            "Example: `https://t.me/channelname/123`",
            parse_mode="markdown",
            disable_web_page_preview=True
        )
        return
    chat_link = state.get("chat_link")
    
    if not chat_link:
        await message.reply("❌ Pehle chat link bhejo!")
        return
    
    target_chat = _get_chat_identifier(target_link)
    chat_identifier = _get_chat_identifier(chat_link)
    if chat_identifier != target_chat:
        await message.reply_text(
            "❌ **Target link same chat ka nahi hai.**\n\n"
            "Sahi chat ka message link bhejo.",
            parse_mode="markdown"
        )
        return
    
    state["target_chat"] = target_chat
    state["step"] = "awaiting_reason"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Spam", callback_data=f"spam:{target_chat}")],
        [InlineKeyboardButton("Violence", callback_data=f"violence:{target_chat}")],
        [InlineKeyboardButton("Porn", callback_data=f"porn:{target_chat}")],
        [InlineKeyboardButton("🔙 Back", callback_data="back")]
    ])
    await message.reply_text(
        f"✅ **Target Confirmed!**\n\n"
        f"📱 Chat: `{chat_link}`\n"
        f"🎯 Target: `{target_chat}`\n\n"
        "**Select Report Type:**",
        reply_markup=keyboard,
        parse_mode="markdown"
    )

@app.on_callback_query(filters.regex(r"(spam|violence|porn):(.*)"))
async def report_reason(client, callback):
    reason_map = {
        "spam": 1,
        "violence": 3,
        "porn": 8
    }
    reason_text = {
        "spam": "Spam",
        "violence": "Violence",
        "porn": "Pornography"
    }
    
    reason_key, target_chat = callback.data.split(":", 1)
    reason = reason_map[reason_key]
    reason_name = reason_text[reason_key]
    
    await callback.message.edit_text(
        f"📝 **Report Details:**\n\n"
        f"Reason: `{reason_name}`\n"
        f"Target: `{target_chat}`\n\n"
        f"**Send Report Description:**"
    )
    app.report_state = {
        "target": target_chat,
        "reason": reason,
        "reason_name": reason_name,
        "user_id": callback.from_user.id
    }
    state = app.user_states.get(callback.from_user.id)
    if state:
        state["step"] = "awaiting_description"

@app.on_message(filters.private & filters.text)
async def handle_description(client, message):
    user_state = app.user_states.get(message.from_user.id)
    if not user_state or user_state.get("step") != "awaiting_description":
        return
    if not await _is_authorized(message.from_user.id):
        app.user_states.pop(message.from_user.id, None)
        await message.reply_text("❌ **Owner/Sudo only.**", parse_mode="markdown")
        return
    if not hasattr(app, 'report_state') or app.report_state['user_id'] != message.from_user.id:
        return
    
    description = message.text
    report_state = app.report_state
    
    await message.reply_text(
        f"✅ **Ready to Report!**\n\n"
        f"🎯 Target: `{report_state['target']}`\n"
        f"⚠️ Reason: `{report_state['reason_name']}`\n"
        f"📝 Description: `{description[:50]}...`\n\n"
        f"**Enter Number of Reports per session:**",
        parse_mode="markdown"
    )
    app.report_description = description
    user_state["step"] = "awaiting_count"

@app.on_message(filters.regex(r"^\d+$") & filters.private)
async def handle_report_count(client, message):
    state = app.user_states.get(message.from_user.id)
    if not state or state.get("step") != "awaiting_count":
        return
    if not await _is_authorized(message.from_user.id):
        app.user_states.pop(message.from_user.id, None)
        await message.reply_text("❌ **Owner/Sudo only.**", parse_mode="markdown")
        return
    if not hasattr(app, 'report_state'):
        return
    
    count = int(message.text)
    state = app.report_state
    description = getattr(app, 'report_description', 'Mass Report')
    
    status_message = await message.reply_text("⏳ **Starting Mass Report...**")
    
    reporter = MassReporter()
    active_count = await reporter.load_validated_sessions()
    if active_count == 0:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Validate Sessions", callback_data="validate_sessions")],
            [InlineKeyboardButton("🔙 Back", callback_data="back")]
        ])
        await message.reply_text(
            "❌ **No active sessions found.**\n\n"
            "Pehle sessions validate karo.",
            reply_markup=keyboard
        )
        return
    
    total_sessions = len(reporter.active_clients)
    last_update = 0.0

    async def update_panel(success_count, failed_count, total_count):
        nonlocal last_update
        now = asyncio.get_event_loop().time()
        should_update = (now - last_update) > 1.0 or (success_count + failed_count) == total_count
        if not should_update:
            return
        last_update = now
        await status_message.edit_text(
            "📊 **Live Reporting Panel**\n\n"
            f"🟢 **Success:** {success_count}\n"
            f"🔴 **Failed:** {failed_count}\n"
            f"📌 **Total Sessions:** {total_count}\n"
            f"🧾 **Reports per session:** {count}\n",
            parse_mode="markdown"
        )

    await update_panel(0, 0, total_sessions)

    success, failed = await reporter.mass_report(
        state['target'], 
        state['reason'], 
        description, 
        count,
        progress_callback=update_panel
    )
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Main Menu", callback_data="back")]
    ])
    
    await message.reply_text(
        f"✅ **Mass Report Complete!**\n\n"
        f"🟢 **Success:** {success}\n"
        f"🔴 **Failed:** {failed}\n"
        f"📊 **Total Sessions:** {success + failed}\n"
        f"🎯 **Reports sent:** {(success * int(message.text))}\n\n"
        f"**Target:** `{state['target']}`",
        reply_markup=keyboard,
        parse_mode="markdown"
    )
    app.user_states.pop(message.from_user.id, None)

@app.on_callback_query(filters.regex(r"add_sudo|remove_sudo"))
async def sudo_manager(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Owner only!", show_alert=True)
        return
    
    if "add_sudo" in callback.data:
        await callback.message.edit_text(
            "👤 **Send User ID to add as Sudo:**",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        )
    else:
        sudos = await db.get_sudos()
        sudo_list = "\n".join([f"`{sudo['user_id']}`" for sudo in sudos])
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
        await callback.message.edit_text(
            f"👥 **Sudo Users:**\n\n{sudo_list or 'No sudos'}\n\n"
            f"**Send User ID to remove:**",
            reply_markup=keyboard,
            parse_mode="markdown"
        )

@app.on_callback_query(filters.regex("stats"))
async def stats(client, callback):
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Owner only!")
        return
    
    active_sessions = await db.get_active_session_count()
    sudos = await db.get_sudos()
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]])
    await callback.message.edit_text(
        f"📊 **Bot Stats:**\n\n"
        f"🟢 Active Sessions: **{active_sessions}**\n"
        f"👥 Sudo Users: **{len(sudos)}**\n"
        f"👑 Owner ID: `{OWNER_ID}`",
        reply_markup=keyboard,
        parse_mode="markdown"
    )

@app.on_callback_query(filters.regex("back"))
async def back(client, callback):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚨 Send Report", callback_data="report_start")]
    ])

    app.user_states.pop(callback.from_user.id, None)
    
    user_id = callback.from_user.id
    if user_id == OWNER_ID or user_id in SUDO_USERS:
        keyboard.inline_keyboard.extend([
            [
                InlineKeyboardButton("➕ Add Sudo", callback_data="add_sudo"),
                InlineKeyboardButton("➖ Remove Sudo", callback_data="remove_sudo")
            ],
            [InlineKeyboardButton("📊 Stats", callback_data="stats")]
        ])
    
    await callback.message.edit_text(
        "🚨 **Mass Report Bot Active!**\n\n"
        "Click **Send Report** to start mass reporting!",
        reply_markup=keyboard
    )

if __name__ == "__main__":
    print("Starting Mass Report Bot...")
    app.run()
