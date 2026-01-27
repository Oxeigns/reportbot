import asyncio
import logging
from pyrogram import Client, filters, raw
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from pyrogram.enums import ParseMode
from config import BOT_TOKEN, OWNER_ID, API_ID, API_HASH
from database import db
from report import reporter, SessionValidator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

client_kwargs = {"bot_token": BOT_TOKEN}
if API_ID and API_HASH:
    client_kwargs.update({"api_id": API_ID, "api_hash": API_HASH})

app = Client("startlove_bot", **client_kwargs)
app.user_states = {}

HACKER_FRAMES = [
    "▰▱▱▱▱",
    "▱▰▱▱▱",
    "▱▱▰▱▱",
    "▱▱▱▰▱",
    "▱▱▱▱▰",
    "▰▰▱▱▱",
    "▱▰▰▱▱",
    "▱▱▰▰▱",
    "▱▱▱▰▰",
    "▰▱▱▱▰",
]

SESSION_VALIDATE_PHASES = [
    "Booting session matrix",
    "Decrypting vault tokens",
    "Cross-checking API keys",
    "Syncing session fingerprints",
    "Finalizing audit pass",
]

JOIN_CHAT_PHASES = [
    "Dialing tunnel nodes",
    "Injecting join handshake",
    "Resolving invite hashes",
    "Confirming membership",
    "Locking signal on target",
]

RESOLVE_CHAT_PHASES = [
    "Parsing deep link",
    "Resolving entity ID",
    "Mapping message trail",
    "Verifying chat access",
    "Preparing report panel",
]

REPORT_REASONS = {
    "spam": ("🚫 SPAM", raw.types.InputReportReasonSpam()),
    "violence": ("⚔️ VIOLENCE", raw.types.InputReportReasonViolence()),
    "porn": ("🔞 PORNOGRAPHY", raw.types.InputReportReasonPornography()),
    "child": ("🧒 CHILD ABUSE", raw.types.InputReportReasonChildAbuse()),
    "drugs": ("💊 ILLEGAL DRUGS", raw.types.InputReportReasonIllegalDrugs()),
    "fake": ("🆔 FAKE", raw.types.InputReportReasonFake()),
    "other": ("❓ OTHER", raw.types.InputReportReasonOther())
}

async def is_authorized(user_id: int) -> bool:
    return user_id == OWNER_ID or await db.is_sudo(user_id)

async def safe_answer(callback: CallbackQuery):
    try:
        await callback.answer()
    except:
        pass

async def animate_message(message, template: str, stop_event: asyncio.Event, interval: float = 1.2):
    frame_index = 0
    while not stop_event.is_set():
        frame = HACKER_FRAMES[frame_index % len(HACKER_FRAMES)]
        try:
            await message.edit_text(
                template.format(frame=frame),
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        await asyncio.sleep(interval)
        frame_index += 1

async def animate_message_with_phases(
    message,
    template: str,
    stop_event: asyncio.Event,
    phases: list[str],
    interval: float = 1.2,
):
    frame_index = 0
    while not stop_event.is_set():
        frame = HACKER_FRAMES[frame_index % len(HACKER_FRAMES)]
        phase = phases[frame_index % len(phases)]
        try:
            await message.edit_text(
                template.format(frame=frame, phase=phase),
                parse_mode=ParseMode.MARKDOWN
            )
        except:
            pass
        await asyncio.sleep(interval)
        frame_index += 1

async def animate_for_duration(
    message,
    template: str,
    duration: float = 2.4,
    interval: float = 0.6,
    phases: list[str] | None = None,
):
    stop_event = asyncio.Event()
    if phases:
        task = asyncio.create_task(
            animate_message_with_phases(message, template, stop_event, phases, interval)
        )
    else:
        task = asyncio.create_task(animate_message(message, template, stop_event, interval))
    try:
        await asyncio.sleep(duration)
    finally:
        stop_event.set()
        await task

def main_keyboard(is_admin: bool = False, is_owner: bool = False):
    keyboard = [
        [InlineKeyboardButton("🚀 START REPORT", callback_data="start_report")],
        [InlineKeyboardButton("📊 STATS", callback_data="stats")]
    ]
    if is_admin:
        keyboard.extend([
            [InlineKeyboardButton("➕ ADD SESSION", callback_data="add_session")],
        ])
    if is_owner:
        keyboard.append([InlineKeyboardButton("👥 SUDOS", callback_data="manage_sudos")])
    keyboard.append([InlineKeyboardButton("ℹ️ HELP", callback_data="help")])
    return InlineKeyboardMarkup(keyboard)

async def build_sudo_panel() -> tuple[str, InlineKeyboardMarkup]:
    sudo_ids = await db.get_sudo_ids()
    if sudo_ids:
        list_text = "\n".join(f"• `{sudo_id}`" for sudo_id in sudo_ids)
    else:
        list_text = "• _No sudos added yet._"

    text = (
        "👥 **SUDO MANAGER**\n\n"
        f"{list_text}\n\n"
        f"**TOTAL:** `{len(sudo_ids)}`"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ ADD SUDO", callback_data="sudo_add")],
        [InlineKeyboardButton("➖ REMOVE SUDO", callback_data="sudo_remove")],
        [InlineKeyboardButton("🔄 REFRESH", callback_data="manage_sudos")],
        [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
    ])
    return text, keyboard

@app.on_message(filters.command("start") & filters.private)
async def start_cmd(client, message):
    is_admin = await is_authorized(message.from_user.id)
    is_owner = message.from_user.id == OWNER_ID
    stats = await db.get_stats()
    
    text = f"""🔥 **STARTLOVE v3.0** ✅

📊 **STATS:**
• `{stats['active']}` Active ✅
• `{stats['pending']}` Pending ⏳
• `{stats['failed']}` Failed ❌
• `{stats['total']}` Total 📈

👤 **You:** {'🔥 ADMIN' if is_admin else '👤 User'}
"""
    
    await message.reply_text(text, reply_markup=main_keyboard(is_admin, is_owner), parse_mode=ParseMode.MARKDOWN)

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
    animation_template = (
        "💻 **SESSION VAULT CHECK**\n\n"
        "⌛ `{frame}` **{phase}**\n"
        "🔐 Verifying keys & sessions\n"
        "🧠 Hold tight, hacking in progress..."
    )
    stop_event = asyncio.Event()
    animation_task = asyncio.create_task(
        animate_message_with_phases(
            callback.message,
            animation_template,
            stop_event,
            SESSION_VALIDATE_PHASES,
            1.1
        )
    )
    
    results = await reporter.validate_all_sessions()
    stop_event.set()
    await animation_task
    stats = await db.get_stats()
    
    emoji = "✅" if stats['active'] > 0 else "⚠️"
    keyboard = main_keyboard(
        await is_authorized(callback.from_user.id),
        callback.from_user.id == OWNER_ID
    )
    
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
    if not reporter.has_api_credentials():
        await callback.message.edit_text(
            "❌ **MISSING API_ID/API_HASH**\n\n"
            "Session validation is required before saving.\n"
            "Set `API_ID` and `API_HASH` in config vars to continue.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]]),
            parse_mode=ParseMode.MARKDOWN
        )
        return
    app.user_states[callback.from_user.id] = {"step": "add_session"}
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]])
    await callback.message.edit_text(
        "📝 **PASTE SESSIONS:**\n\n"
        "• **One per line**\n"
        "• **Pyrogram v2** (`1BV...`)\n\n"
        "`1BVABC...`\n`1BVDEF...`\n`1BVXYZ...`\n\n"
        "**Each session will be validated before saving.**\n"
        "**Send now!**",
        reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^start_report$"))
async def start_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    await callback.message.edit_text(
        "🚀 **START REPORTING**\n\n"
        "Choose an option below:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ ADD NEW SESSION", callback_data="add_session")],
            [InlineKeyboardButton("✅ REPORT WITH SAVED SESSIONS", callback_data="report_saved")],
            [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
        ])
    )

@app.on_callback_query(filters.regex("^report_saved$"))
async def report_saved_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    if not reporter.has_api_credentials():
        await callback.message.edit_text(
            "❌ **MISSING API_ID/API_HASH**\n\n"
            "Set `API_ID` and `API_HASH` in config vars before reporting."
        )
        return

    animation_template = (
        "🧬 **PREPARING SAVED SESSIONS**\n\n"
        "⚙️ `{frame}` **{phase}**\n"
        "📡 Syncing saved sessions for report run\n"
        "💫 Please wait, warming up..."
    )
    stop_event = asyncio.Event()
    animation_task = asyncio.create_task(
        animate_message_with_phases(
            callback.message,
            animation_template,
            stop_event,
            SESSION_VALIDATE_PHASES,
            1.0
        )
    )
    await reporter.validate_all_sessions()
    stop_event.set()
    await animation_task
    stats = await db.get_stats()

    if stats["active"] < 1:
        await callback.message.edit_text(
            "❌ **NO ACTIVE SESSIONS FOUND!**\n\n"
            "➕ Add at least 1 session to continue.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ ADD SESSION", callback_data="add_session")],
                [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
            ])
        )
        return

    app.user_states[callback.from_user.id] = {"step": "join_chat_link"}
    await callback.message.edit_text(
        f"✅ **{stats['active']} SESSIONS READY!** 🔥\n\n"
        "🔗 **CHAT LINK TO JOIN:**\n\n"
        "`https://t.me/+invite`\n`https://t.me/username`",
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
        if not reporter.has_api_credentials():
            await message.reply_text(
                "❌ **MISSING API_ID/API_HASH**\n\n"
                "Session validation is required before saving.\n"
                "Set `API_ID` and `API_HASH` in config vars to continue.",
                reply_markup=main_keyboard(True, user_id == OWNER_ID),
                parse_mode=ParseMode.MARKDOWN
            )
            del app.user_states[user_id]
            return
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        success_count = 0
        active_count = 0
        declined_count = 0
        failed_count = 0
        base_count = await db.get_total_session_count()
        
        for session in lines:
            if not db.is_valid_session_string(session):
                declined_count += 1
                continue
            session_name = f"session_{base_count + success_count + 1}"
            validated, error = await SessionValidator.test_session(session, session_name)
            if not validated:
                declined_count += 1
                continue
            ok, msg = await db.add_session(session, session_name)
            if not ok:
                failed_count += 1
                continue
            await db.update_session_status(session_name, "active", None)
            success_count += 1
            active_count += 1
        
        stats = await db.get_stats()
        keyboard = main_keyboard(True, user_id == OWNER_ID)
        
        await message.reply_text(
            f"✅ **{success_count}/{len(lines)} SAVED!**\n\n"
            f"🟢 `{active_count}` Active | 🚫 `{declined_count}` Declined | ❌ `{failed_count}` Failed\n"
            f"📊 `{stats['active']}` Active | `{stats['total']}` Total",
            reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN
        )
        del app.user_states[user_id]

    elif state["step"] == "add_sudo":
        if user_id != OWNER_ID:
            await message.reply_text("❌ **ONLY OWNER CAN ADD SUDOS**", parse_mode=ParseMode.MARKDOWN)
            del app.user_states[user_id]
            return
        if not text.isdigit():
            await message.reply_text(
                "❌ **INVALID USER ID**\n\nSend a numeric user ID.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        target_id = int(text)
        if target_id == OWNER_ID:
            await message.reply_text(
                "⚠️ **OWNER IS ALWAYS ADMIN.**",
                parse_mode=ParseMode.MARKDOWN
            )
            del app.user_states[user_id]
            return
        if await db.is_sudo(target_id):
            await message.reply_text(
                "⚠️ **USER ALREADY SUDO.**",
                parse_mode=ParseMode.MARKDOWN
            )
            del app.user_states[user_id]
            return
        await db.add_sudo(target_id)
        text, keyboard = await build_sudo_panel()
        await message.reply_text(
            f"✅ **SUDO ADDED:** `{target_id}`\n\n{text}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        del app.user_states[user_id]

    elif state["step"] == "remove_sudo":
        if user_id != OWNER_ID:
            await message.reply_text("❌ **ONLY OWNER CAN REMOVE SUDOS**", parse_mode=ParseMode.MARKDOWN)
            del app.user_states[user_id]
            return
        if not text.isdigit():
            await message.reply_text(
                "❌ **INVALID USER ID**\n\nSend a numeric user ID.",
                parse_mode=ParseMode.MARKDOWN
            )
            return
        target_id = int(text)
        if target_id == OWNER_ID:
            await message.reply_text(
                "⚠️ **OWNER CANNOT BE REMOVED.**",
                parse_mode=ParseMode.MARKDOWN
            )
            del app.user_states[user_id]
            return
        if not await db.is_sudo(target_id):
            await message.reply_text(
                "⚠️ **USER NOT IN SUDO LIST.**",
                parse_mode=ParseMode.MARKDOWN
            )
            del app.user_states[user_id]
            return
        await db.remove_sudo(target_id)
        text, keyboard = await build_sudo_panel()
        await message.reply_text(
            f"✅ **SUDO REMOVED:** `{target_id}`\n\n{text}",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        del app.user_states[user_id]

    elif state["step"] == "join_chat_link":
        if not reporter.has_api_credentials():
            await message.reply_text(
                "❌ **MISSING API_ID/API_HASH**\n\n"
                "Set `API_ID` and `API_HASH` in config vars before reporting."
            )
            del app.user_states[user_id]
            return
        join_link = text
        await reporter.load_active_clients()
        animation_template = (
            "🛰️ **INFILTRATING CHAT**\n\n"
            "🔌 `{frame}` **{phase}**\n"
            "🧭 Syncing sessions & join requests\n"
            "⚠️ Do not close the panel..."
        )
        status_message = await message.reply_text(
            animation_template.format(frame=HACKER_FRAMES[0], phase=JOIN_CHAT_PHASES[0]),
            parse_mode=ParseMode.MARKDOWN
        )
        stop_event = asyncio.Event()
        animation_task = asyncio.create_task(
            animate_message_with_phases(
                status_message,
                animation_template,
                stop_event,
                JOIN_CHAT_PHASES,
                1.0
            )
        )
        joined = await reporter.join_target_chat(join_link)
        stop_event.set()
        await animation_task
        app.user_states[user_id] = {
            "step": "target_chat_link",
            "join_link": join_link
        }

        await status_message.edit_text(
            f"✅ **JOINED:** {joined}/{len(reporter.active_clients)}\n\n"
            "🔗 **SEND TARGET CHAT OR MESSAGE LINK:**\n\n"
            "`@username`\n`t.me/username`\n"
            "`t.me/username/123`",
            parse_mode=ParseMode.MARKDOWN
        )

    elif state["step"] == "target_chat_link":
        animation_template = (
            "🔎 **RESOLVING TARGET**\n\n"
            "🧩 `{frame}` **{phase}**\n"
            "🛰️ Mapping chat routes\n"
            "💡 Almost there..."
        )
        status_message = await message.reply_text(
            animation_template.format(frame=HACKER_FRAMES[0], phase=RESOLVE_CHAT_PHASES[0]),
            parse_mode=ParseMode.MARKDOWN
        )
        await animate_for_duration(
            status_message,
            animation_template,
            2.7,
            0.6,
            RESOLVE_CHAT_PHASES
        )
        chat_id, message_ids = parse_report_target(text)
        app.user_states[user_id] = {
            "step": "report_type",
            "target": chat_id,
            "message_ids": message_ids
        }

        reason_rows = []
        reason_items = list(REPORT_REASONS.items())
        for i in range(0, len(reason_items), 2):
            row = []
            for key, (label, _) in reason_items[i:i + 2]:
                row.append(InlineKeyboardButton(label, callback_data=f"report_reason:{key}"))
            reason_rows.append(row)
        reason_rows.append([InlineKeyboardButton("🏠 MAIN", callback_data="home")])

        message_line = ""
        if message_ids:
            message_line = f"\n🧾 **MESSAGE ID:** `{message_ids[0]}`"

        await status_message.edit_text(
            f"🎯 **RESOLVED CHAT:** `{chat_id}`{message_line}\n\n"
            "📝 **SELECT REPORT TYPE:**",
            reply_markup=InlineKeyboardMarkup(reason_rows),
            parse_mode=ParseMode.MARKDOWN
        )

    elif state["step"] == "report_description":
        description = text
        app.user_states[user_id] = {
            "step": "report_count",
            "target": state["target"],
            "reason_key": state["reason_key"],
            "description": description,
            "message_ids": state.get("message_ids")
        }
        available = len(reporter.active_clients)
        await message.reply_text(
            "✅ **DESCRIPTION SAVED!**\n\n"
            "🔢 **HOW MANY REPORT ATTEMPTS?**\n"
            f"• Available sessions: `{available}`\n"
            "• Each attempt uses one session (round-robin)\n"
            "• Send a number (e.g., `3`)",
            parse_mode=ParseMode.MARKDOWN
        )

    elif state["step"] == "report_count":
        try:
            requested = int(text)
        except ValueError:
            await message.reply_text(
                "❌ **INVALID NUMBER**\n\n"
                "Send a valid integer (e.g., `10`).",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if requested < 1:
            await message.reply_text(
                "❌ **NUMBER MUST BE >= 1**\n\n"
                "Send a valid integer (e.g., `10`).",
                parse_mode=ParseMode.MARKDOWN
            )
            return

        if not reporter.active_clients:
            await message.reply_text(
                "❌ **NO ACTIVE SESSIONS FOUND!**\n\n"
                "➕ Add at least 1 session to continue.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("➕ ADD SESSION", callback_data="add_session")],
                    [InlineKeyboardButton("🏠 MAIN", callback_data="home")]
                ])
            )
            del app.user_states[user_id]
            return

        reason_key = state["reason_key"]
        reason = REPORT_REASONS.get(reason_key, REPORT_REASONS["spam"])[1]
        chat_id = state["target"]
        description = state.get("description", "")
        message_ids = state.get("message_ids")
        available = len(reporter.active_clients)
        attempts = requested

        status_message = await message.reply_text("🔥 **REPORTING...**", parse_mode=ParseMode.MARKDOWN)

        async def update_progress(attempt, total_attempts, results):
            await status_message.edit_text(
                "📊 **LIVE PANEL**\n\n"
                f"🧪 **ATTEMPT:** `{attempt}/{total_attempts}`\n"
                f"✅ **ATTEMPTS SUCCESS:** `{results['attempt_success']}`\n"
                f"❌ **ATTEMPTS FAILED:** `{results['attempt_failed']}`\n"
                f"📈 **REPORTS SUCCESS:** `{results['success']}`\n"
                f"📉 **REPORTS FAILED:** `{results['failed']}`\n"
                f"🧾 **REPORTS TOTAL:** `{results['total']}`\n\n"
                f"🎯 **{chat_id}**",
                parse_mode=ParseMode.MARKDOWN
            )

        if message_ids:
            results = await reporter.mass_report_message(
                chat_id,
                message_ids=message_ids,
                reason=reason,
                description=description,
                attempts=attempts,
                on_progress=update_progress
            )
        else:
            results = await reporter.mass_report_chat(
                chat_id,
                reason=reason,
                description=description,
                attempts=attempts,
                on_progress=update_progress
            )

        keyboard = main_keyboard(await is_authorized(user_id), user_id == OWNER_ID)
        text = f"""🎉 **REPORT FINISHED!**

🧪 **ATTEMPTS:** `{attempts}`
✅ **ATTEMPTS SUCCESS:** `{results['attempt_success']}`
❌ **ATTEMPTS FAILED:** `{results['attempt_failed']}`
📊 **TOTAL REPORTS:** `{results['total']}`
✅ **SUCCESS:** `{results['success']}`
❌ **FAILED:** `{results['failed']}`
📈 **TOTAL:** `{results['total']}`

🎯 **{chat_id}**
"""
        await status_message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)
        del app.user_states[user_id]

def get_chat_id(link: str) -> str:
    link = link.split("?")[0].strip()
    if "/joinchat/" in link:
        return link.split("/joinchat/")[1]
    if "t.me/" in link:
        parts = link.split("t.me/")[1].split("/")
        username = parts[0].strip()
        return f"@{username}" if not username.startswith("@") else username
    return link.lstrip("@")

def parse_report_target(link: str) -> tuple[str, list[int] | None]:
    cleaned = link.split("?")[0].strip()

    if "t.me/c/" in cleaned:
        parts = cleaned.split("t.me/c/")[1].split("/")
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            return f"-100{parts[0]}", [int(parts[1])]

    if "t.me/" in cleaned:
        parts = cleaned.split("t.me/")[1].split("/")
        username = parts[0].strip()
        if len(parts) >= 2 and parts[1].isdigit():
            chat_id = f"@{username}" if not username.startswith("@") else username
            return chat_id, [int(parts[1])]

    return get_chat_id(cleaned), None

@app.on_callback_query(filters.regex("^report_reason:"))
async def report_reason_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    user_id = callback.from_user.id
    state = app.user_states.get(user_id)
    if not state or state.get("step") != "report_type":
        await callback.answer("⚠️ No active report.", show_alert=True)
        return

    reason_key = callback.data.split(":", 1)[1]
    if reason_key not in REPORT_REASONS:
        await callback.answer("⚠️ Invalid report type.", show_alert=True)
        return

    chat_id = state["target"]
    message_ids = state.get("message_ids")
    reason_label = REPORT_REASONS[reason_key][0]
    app.user_states[user_id] = {
        "step": "report_description",
        "target": chat_id,
        "reason_key": reason_key,
        "message_ids": message_ids
    }

    await callback.message.edit_text(
        f"✅ **TYPE SELECTED:** {reason_label}\n\n"
        f"🎯 **{chat_id}**\n\n"
        "📝 **SEND REPORT DESCRIPTION:**",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^mass_report\\|"))
async def mass_report_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    await callback.answer("⚠️ Please follow the new report flow.", show_alert=True)

@app.on_callback_query(filters.regex("^manage_sudos$"))
async def manage_sudos_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Only the owner can manage sudos.", show_alert=True)
        return
    text, keyboard = await build_sudo_panel()
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)

@app.on_callback_query(filters.regex("^sudo_add$"))
async def sudo_add_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Only the owner can add sudos.", show_alert=True)
        return
    app.user_states[callback.from_user.id] = {"step": "add_sudo"}
    await callback.message.edit_text(
        "➕ **ADD SUDO**\n\n"
        "Send the user ID to grant sudo access.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^sudo_remove$"))
async def sudo_remove_callback(client, callback: CallbackQuery):
    await safe_answer(callback)
    if callback.from_user.id != OWNER_ID:
        await callback.answer("❌ Only the owner can remove sudos.", show_alert=True)
        return
    app.user_states[callback.from_user.id] = {"step": "remove_sudo"}
    await callback.message.edit_text(
        "➖ **REMOVE SUDO**\n\n"
        "Send the user ID to revoke sudo access.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🏠 MAIN", callback_data="home")]]),
        parse_mode=ParseMode.MARKDOWN
    )

@app.on_callback_query(filters.regex("^(home|help)$"))
async def other_callbacks(client, callback: CallbackQuery):
    await safe_answer(callback)
    await callback.answer("🔥 Coming soon!", show_alert=True)

if __name__ == "__main__":
    print("🚀 STARTLOVE v3.0 - ULTIMATE ✅")
    app.run()
