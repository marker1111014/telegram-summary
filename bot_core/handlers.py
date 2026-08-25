"""PTB command/message handlers."""
import logging
import re
from datetime import datetime, timezone
from typing import List, Optional

from telegram import Update, constants
from telegram.ext import ContextTypes

# NOTE: import modules (not symbols) so tests can monkeypatch
# summarizer.generate_summary on the source module.
from bot_core import cache, config, summarizer

logger = logging.getLogger(__name__)

HELP_TEXT = (
    "Hi! I summarize recent messages in this group.\n\n"
    f"Use `/summarize [N]` to summarize the last N messages "
    f"(default {config.DEFAULT_SUMMARY_MESSAGES}, max {config.MAX_SUMMARY_MESSAGES}).\n"
    "Example: `/summarize 50`\n\n"
    f"I only remember messages sent while I'm running (up to {config.MESSAGE_CACHE_SIZE} per chat)."
)

ERROR_TEXT = "❌ Something went wrong while generating the summary."


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    await update.message.reply_text(
        HELP_TEXT,
        parse_mode=constants.ParseMode.MARKDOWN,
        disable_web_page_preview=True,
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.from_user is None or message.chat is None:
        return
    user = message.from_user
    msg = {
        "message_id": message.message_id,
        "user_id": user.id,
        "user_name": user.full_name or user.first_name or str(user.id),
        "username": user.username,
        "text": message.text or "",
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    try:
        cache.cache_message(message.chat.id, msg)
    except Exception:
        logger.error("Failed to cache message for chat %s", message.chat.id, exc_info=True)


def _parse_count(args: Optional[List[str]]) -> int:
    if not args:
        return config.DEFAULT_SUMMARY_MESSAGES
    arg = args[0].strip()
    if not arg.isdigit():
        return config.DEFAULT_SUMMARY_MESSAGES
    return min(max(int(arg), 1), config.MAX_SUMMARY_MESSAGES)


async def _deliver(target_message, source_message, text: str) -> None:
    """Edit the processing message (or reply fresh), falling back to plain text."""
    try:
        if target_message is not None:
            await target_message.edit_text(text=text, parse_mode=constants.ParseMode.MARKDOWN,
                                           disable_web_page_preview=True)
        else:
            await source_message.reply_text(text=text, parse_mode=constants.ParseMode.MARKDOWN,
                                            disable_web_page_preview=True)
    except Exception:
        plain = re.sub(r"[*_\[\]()`]", "", text)
        try:
            if target_message is not None:
                await target_message.edit_text(text=plain, disable_web_page_preview=True)
            else:
                await source_message.reply_text(text=plain, disable_web_page_preview=True)
        except Exception:
            logger.error("Failed to deliver summary message", exc_info=True)


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.chat is None:
        return
    chat = message.chat
    if chat.type not in (constants.ChatType.GROUP, constants.ChatType.SUPERGROUP):
        return

    num = _parse_count(context.args)

    processing = None
    try:
        processing = await message.reply_text(
            f"⏳ Summarizing the last {num} cached messages… please wait.",
            disable_notification=True,
        )
    except Exception:
        logger.error("Failed to send processing message in chat %s", chat.id, exc_info=True)
        return

    try:
        messages = cache.get_recent_messages(chat.id, num)
        if not messages:
            await _deliver(processing, message,
                           "I don't have any cached messages for this chat yet. "
                           "Send some messages first, then try again!")
            return
        summary = await summarizer.generate_summary(messages)
        if len(summary) > 4096:
            summary = summary[:4093] + "..."
        await _deliver(processing, message, summary)
    except summarizer.SummaryError as e:
        await _deliver(processing, message, e.user_message)
    except Exception:
        logger.error("Unexpected error during /summarize in chat %s", chat.id, exc_info=True)
        await _deliver(processing, message, ERROR_TEXT)
