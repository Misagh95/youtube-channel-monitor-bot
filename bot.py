"""
YouTube Channel Monitor Bot
Monitors YouTube channels via RSS and sends new video alerts.
"""
import os
import asyncio
import logging
import feedparser
import html
import re
from typing import Any, Optional

from dotenv import load_dotenv
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID", "")
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "300"))
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "20"))

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

sources: dict = {}
known: set = set()


def is_admin(chat_id: Any) -> bool:
    if not ADMIN_CHAT_ID:
        return True
    return str(chat_id) in ADMIN_CHAT_ID.split(",")


def clean_url(channel: str) -> str:
    if channel.startswith("UC"):
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel}"
    if "/" in channel or "youtube" in channel.lower():
        return channel
    return f"https://www.youtube.com/feeds/videos.xml?user={channel}"


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    await update.message.reply_text(
        "📺 YouTube Channel Monitor\n\n"
        "/add <channel_id> - Add channel\n"
        "/remove <channel_id> - Remove channel\n"
        "/list - List channels\n"
        "/status - Status"
    )


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /add <channel_id>")
        return
    cid = context.args[0]
    url = clean_url(cid)
    try:
        feed = feedparser.parse(url)
        if not feed.entries:
            await update.message.reply_text("❌ Channel not found or no videos.")
            return
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")
        return
    chat_id = update.effective_chat.id
    sources.setdefault(chat_id, set()).add(cid)
    await update.message.reply_text(f"✅ Added {cid}.")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    if not is_admin(update.effective_chat.id):
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: /remove <channel_id>")
        return
    cid = context.args[0]
    chat_id = update.effective_chat.id
    if chat_id in sources and cid in sources[chat_id]:
        sources[chat_id].remove(cid)
        await update.message.reply_text(f"✅ Removed {cid}.")
    else:
        await update.message.reply_text("❌ Not found.")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    chat_id = update.effective_chat.id
    chs = sources.get(chat_id, set())
    if not chs:
        await update.message.reply_text("📭 No channels.")
        return
    await update.message.reply_text("📺 Channels:\n" + "\n".join(f"• {c}" for c in chs))


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_chat or not update.message:
        return
    total = sum(len(v) for v in sources.values())
    await update.message.reply_text(f"📊 Total monitored channels: {total}")


async def monitor(app: Application) -> None:
    while True:
        try:
            all_channels = set()
            for chs in sources.values():
                all_channels.update(chs)
            for cid in all_channels:
                try:
                    feed = feedparser.parse(clean_url(cid))
                    for entry in feed.entries:
                        vid = entry.get("yt_videoid") or entry.get("id")
                        if vid in known:
                            break
                        known.add(vid)
                        title = html.unescape(entry.get("title", "New Video"))
                        link = entry.get("link", "")
                        text = f"📺 <b>New Video</b>\n\n<b>{title}</b>\n\n<a href='{link}'>Watch</a>"
                        for chat_id, chs in sources.items():
                            if cid in chs:
                                try:
                                    await app.bot.send_message(chat_id=chat_id, text=text, parse_mode="HTML")
                                except Exception as e:
                                    logger.warning(f"Send failed: {e}")
                                await asyncio.sleep(0.3)
                except Exception as e:
                    logger.warning(f"Channel fetch failed {cid}: {e}")
        except Exception as e:
            logger.error(f"Monitor error: {e}")
        await asyncio.sleep(CHECK_INTERVAL)


async def post_init(application: Application) -> None:
    asyncio.create_task(monitor(application))
    commands = [BotCommand("start", "Start"), BotCommand("add", "Add channel"), BotCommand("remove", "Remove channel"), BotCommand("list", "List channels"), BotCommand("status", "Status")]
    await application.bot.set_my_commands(commands)


def main() -> None:
    if not TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN missing!")
        return
    application = Application.builder().token(TOKEN).post_init(post_init).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("remove", cmd_remove))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("status", cmd_status))
    application.run_polling()


if __name__ == "__main__":
    main()
