#!/usr/bin/env python3

import re
import asyncio
import json
import os
from pathlib import Path
from aiohttp import web

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ================= CONFIG =================

BOT_TOKEN = "8518386618:AAE5r3MosrqHGXp93IpFA_mCOQMbV_lGJTc"

CHANNEL_ID = -1002943476061
OWNER_ID = 6324705417

BLACKLIST_FILE = "blacklist.json"

PORT = int(os.environ.get("PORT", 10000))
WEBHOOK_PATH = "/webhook"

# ================= SETTINGS =================

spam_delay = 30
anti_spam_enabled = True
user_last_message = {}

auto_delete_enabled = False
auto_delete_time = 0

blacklisted_words = set()

gn_active = False
gn_task = None

# ================= STORAGE =================

def load_blacklist():
    global blacklisted_words

    if Path(BLACKLIST_FILE).exists():
        with open(BLACKLIST_FILE, "r") as f:
            blacklisted_words = set(json.load(f))


def save_blacklist():
    with open(BLACKLIST_FILE, "w") as f:
        json.dump(list(blacklisted_words), f)

# ================= TIME PARSER =================

def parse_time(time_str: str):

    match = re.fullmatch(r"(\d+)([smhd])", time_str.lower())

    if not match:
        return None

    value = int(match.group(1))
    unit = match.group(2)

    multipliers = {
        "s": 1,
        "m": 60,
        "h": 3600,
        "d": 86400
    }

    return value * multipliers[unit]

# ================= OWNER CHECK =================

def is_owner(update: Update):

    return (
        update.effective_chat.type == "private"
        and update.effective_user.id == OWNER_ID
    )

# ================= START PANEL =================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_chat.type != "private":
        return

    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("🤖 Bot Active.")
        return

    await update.message.reply_text(
        "🔥 Channel Control Panel\n\n"
        "Anti-Spam:\n"
        "`/setdelay`  60s\n"
        "`/on`\n"
        "`/off`\n\n"
        "Auto-Delete:\n"
        "`/setdelete`  10m\n"
        "`/deleteon`\n"
        "`/deleteoff`\n\n"
        "Blacklist:\n"
        "`/blacklist`  word\n"
        "`/blacklists`\n"
        "`/rmword`  word\n\n"
        "GN Mode:\n"
        "`/gn`  1h\n"
        "`/gnoff`\n\n",
    parse_mode="Markdown"
)
    
# ================= ANTI-SPAM =================

async def set_delay(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global spam_delay

    if not is_owner(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /setdelay 60s")
        return

    delay = parse_time(context.args[0])

    if not delay:
        await update.message.reply_text("Invalid format")
        return

    spam_delay = delay

    await update.message.reply_text(f"Delay set to {context.args[0]}")


async def turn_on(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global anti_spam_enabled

    if is_owner(update):
        anti_spam_enabled = True
        await update.message.reply_text("Anti-spam ON")


async def turn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global anti_spam_enabled

    if is_owner(update):
        anti_spam_enabled = False
        await update.message.reply_text("Anti-spam OFF")

# ================= AUTO DELETE =================

async def set_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global auto_delete_time

    if not is_owner(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /setdelete  10m")
        return

    delete_time = parse_time(context.args[0])

    if not delete_time:
        await update.message.reply_text("Invalid format")
        return

    auto_delete_time = delete_time

    await update.message.reply_text(f"Auto delete set to {context.args[0]}")


async def delete_on(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global auto_delete_enabled

    if is_owner(update):
        auto_delete_enabled = True
        await update.message.reply_text("Auto delete ON")


async def delete_off(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global auto_delete_enabled

    if is_owner(update):
        auto_delete_enabled = False
        await update.message.reply_text("Auto delete OFF")

# ================= STATUS =================

async def get_status(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update):
        return

    await update.message.reply_text(
        f"Anti-spam: {'ON' if anti_spam_enabled else 'OFF'}\n"
        f"Delay: {spam_delay} sec\n\n"
        f"Auto-delete: {'ON' if auto_delete_enabled else 'OFF'}\n"
        f"Delete time: {auto_delete_time} sec\n\n"
        f"GN Mode: {'ON' if gn_active else 'OFF'}"
    )
    
# ================= BLACKLIST =================

async def blacklist_add(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /blacklist word")
        return

    word = context.args[0].lower()

    blacklisted_words.add(word)

    save_blacklist()

    await update.message.reply_text(f"Added {word}")


async def blacklist_view(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update):
        return

    if not blacklisted_words:
        await update.message.reply_text("Blacklist empty")
        return

    words = "\n".join(sorted(blacklisted_words))

    await update.message.reply_text(words)


async def blacklist_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if not is_owner(update):
        return

    if not context.args:
        return

    word = context.args[0].lower()

    if word in blacklisted_words:

        blacklisted_words.remove(word)

        save_blacklist()

        await update.message.reply_text(f"Removed {word}")

# ================= GN MODE =================

async def gn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global gn_active, gn_task

    if not is_owner(update):
        return

    if not context.args:
        await update.message.reply_text("Usage: /gn  1h")
        return

    duration = parse_time(context.args[0])

    if not duration:
        await update.message.reply_text("Invalid time")
        return

    if gn_active:
        await update.message.reply_text("GN already active")
        return

    gn_active = True

    await update.message.reply_text(f"GN mode for {context.args[0]}")

    gn_task = asyncio.create_task(end_gn_after(duration))


async def end_gn_after(duration):

    global gn_active, anti_spam_enabled, auto_delete_enabled

    await asyncio.sleep(duration)

    gn_active = False
    anti_spam_enabled = True
    auto_delete_enabled = True
    
# ================= GN OFF =================

async def gn_off(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global gn_active, gn_task

    if not is_owner(update):
        return

    if not gn_active:
        await update.message.reply_text("GN mode already OFF")
        return

    gn_active = False

    if gn_task:
        gn_task.cancel()
        gn_task = None

    await update.message.reply_text("GN mode turned OFF")

# ================= DELETE SAFE =================

async def safe_delete(message):

    try:
        await message.delete()
    except:
        pass
async def delete_later(context, chat_id, message_id):

    await asyncio.sleep(auto_delete_time)

    try:
        await context.bot.delete_message(chat_id, message_id)
    except:
        pass
# ================= CHANNEL HANDLER =================

async def handle_channel_post(update: Update, context: ContextTypes.DEFAULT_TYPE):

    global user_last_message

    message = update.channel_post or update.edited_channel_post

    if not message:
        return

    if message.chat.id != CHANNEL_ID:
        return

    if gn_active:
        await safe_delete(message)
        return

    text = (message.text or message.caption or "").lower()

    for word in blacklisted_words:
        if re.search(rf"\b{re.escape(word)}\b", text):
            await safe_delete(message)
            return

    user_id = (
        message.from_user.id
        if message.from_user
        else message.sender_chat.id if message.sender_chat
        else None
    )

    if not user_id:
        return

    current_time = message.date.timestamp()

    last_time = user_last_message.get(user_id)

    if anti_spam_enabled and last_time:
        if current_time - last_time < spam_delay:
            await safe_delete(message)
            return

    user_last_message[user_id] = current_time

    if len(user_last_message) > 5000:
        user_last_message.clear()

    if auto_delete_enabled and auto_delete_time > 0:
        asyncio.create_task(
            delete_later(
                context,
                message.chat.id,
                message.message_id
            )
        )
        
# ================= MAIN =================

async def main():

    load_blacklist()
    
    app = ApplicationBuilder().token(BOT_TOKEN).concurrent_updates(True).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setdelay", set_delay))
    app.add_handler(CommandHandler("on", turn_on))
    app.add_handler(CommandHandler("off", turn_off))

    app.add_handler(CommandHandler("setdelete", set_delete))
    app.add_handler(CommandHandler("deleteon", delete_on))
    app.add_handler(CommandHandler("deleteoff", delete_off))

    app.add_handler(CommandHandler("blacklist", blacklist_add))
    app.add_handler(CommandHandler("blacklists", blacklist_view))
    app.add_handler(CommandHandler("getdelay", get_status))
    app.add_handler(CommandHandler("rmword", blacklist_remove))

    app.add_handler(CommandHandler("gn", gn_command))
    app.add_handler(CommandHandler("gnoff", gn_off))

    app.add_handler(
        MessageHandler(
              filters.ChatType.CHANNEL,
              handle_channel_post
    )
)

    await app.initialize()
    await app.start()

    base_url = os.environ.get("RENDER_EXTERNAL_URL")

    if not base_url:
        raise RuntimeError("RENDER_EXTERNAL_URL not found")

    webhook_url = base_url + WEBHOOK_PATH

    await app.bot.delete_webhook(drop_pending_updates=True)
    await app.bot.set_webhook(webhook_url)

    # ================= WEBHOOK SERVER =================

    async def telegram_webhook(request):
        data = await request.json()
        update = Update.de_json(data, app.bot)
        await app.process_update(update)
        return web.Response()

    web_app = web.Application()
    web_app.router.add_post(WEBHOOK_PATH, telegram_webhook)

    runner = web.AppRunner(web_app)
    await runner.setup()

    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()

    print("Bot running webhook")

    while True:
        await asyncio.sleep(3600)


if __name__ == "__main__":
    asyncio.run(main())