"""PTB command/message handlers."""
import asyncio
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

    threshold = config.AUTO_SUMMARY_THRESHOLD
    if threshold <= 0:
        return
    try:
        count = cache.incr_auto_summary_counter(message.chat.id)
    except Exception:
        logger.error("Failed to increment auto-summary counter for chat %s",
                     message.chat.id, exc_info=True)
        return
    if count == threshold:
        cache.reset_auto_summary_counter(message.chat.id)
        _spawn_auto_summary(message.chat.id, threshold, context.bot)


# ---------- automatic periodic summary ----------

_auto_tasks: set = set()


async def run_auto_summary(chat_id: int, num: int, bot) -> None:
    """Summarize the last `num` cached messages and post them to the chat."""
    remaining = cache.try_acquire_summary_slot(chat_id, config.SUMMARIZE_COOLDOWN_SECONDS)
    if remaining:
        logger.info("Auto summary for chat %s skipped; slot busy for %ss.", chat_id, remaining)
        return
    try:
        messages = cache.get_recent_messages(chat_id, num)
        if not messages:
            cache.release_summary_slot(chat_id)
            return
        summary = await summarizer.generate_summary(messages)
        header = f"🤖 *自動摘要*（每 {num} 則訊息）\n\n"
        text = header + summary
        if len(text) > 4096:
            text = text[:4093] + "..."
        notice = f"\n\n⏳ 此總結將在 {config.SUMMARY_AUTO_DELETE_SECONDS} 秒後自動刪除。"
        try:
            sent = await bot.send_message(chat_id=chat_id, text=text + notice,
                                          parse_mode=constants.ParseMode.MARKDOWN,
                                          disable_web_page_preview=True)
        except Exception:
            plain = re.sub(r"[*_\[\]()`]", "", text + notice)
            sent = await bot.send_message(chat_id=chat_id, text=plain,
                                          disable_web_page_preview=True)
        await asyncio.sleep(config.SUMMARY_AUTO_DELETE_SECONDS)
        try:
            await bot.delete_message(chat_id=chat_id, message_id=sent.message_id)
        except Exception:
            logger.error("Failed to auto-delete auto-summary %s in chat %s",
                         sent.message_id, chat_id, exc_info=True)
    except summarizer.SummaryError as e:
        cache.release_summary_slot(chat_id)
        logger.warning("Auto summary for chat %s failed: %s", chat_id, e.user_message)
    except Exception:
        cache.release_summary_slot(chat_id)
        logger.error("Auto summary for chat %s failed unexpectedly", chat_id, exc_info=True)


def _spawn_auto_summary(chat_id: int, num: int, bot) -> None:
    """Run the auto summary as a background task so the webhook can return immediately."""
    task = asyncio.create_task(run_auto_summary(chat_id, num, bot))
    _auto_tasks.add(task)
    task.add_done_callback(_auto_tasks.discard)


def _parse_count(args: Optional[List[str]]) -> int:
    if not args:
        return config.DEFAULT_SUMMARY_MESSAGES
    arg = args[0].strip()
    if not arg.isdecimal():
        return config.DEFAULT_SUMMARY_MESSAGES
    return min(max(int(arg), 1), config.MAX_SUMMARY_MESSAGES)


async def _deliver(target_message, source_message, text: str):
    """Edit the processing message (or reply fresh), falling back to plain text.

    Returns the delivered Message (for later deletion), or None on total failure.
    """
    try:
        if target_message is not None:
            await target_message.edit_text(text=text, parse_mode=constants.ParseMode.MARKDOWN,
                                           disable_web_page_preview=True)
            return target_message
        return await source_message.reply_text(text=text, parse_mode=constants.ParseMode.MARKDOWN,
                                               disable_web_page_preview=True)
    except Exception:
        plain = re.sub(r"[*_\[\]()`]", "", text)
        try:
            if target_message is not None:
                await target_message.edit_text(text=plain, disable_web_page_preview=True)
                return target_message
            return await source_message.reply_text(text=plain, disable_web_page_preview=True)
        except Exception:
            logger.error("Failed to deliver summary message", exc_info=True)
            return None


async def summarize_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None or message.chat is None:
        return
    chat = message.chat
    if chat.type not in (constants.ChatType.GROUP, constants.ChatType.SUPERGROUP):
        return

    num = _parse_count(context.args)

    remaining = cache.try_acquire_summary_slot(chat.id, config.SUMMARIZE_COOLDOWN_SECONDS)
    if remaining:
        try:
            await message.reply_text(
                f"⏳ 已有摘要正在產生或冷卻中，請約 {remaining} 秒後再試。",
                disable_notification=True,
            )
        except Exception:
            logger.warning("Failed to send cooldown notice in chat %s", chat.id, exc_info=True)
        return

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
            cache.release_summary_slot(chat.id)
            await _deliver(processing, message,
                           "I don't have any cached messages for this chat yet. "
                           "Send some messages first, then try again!")
            return
        summary = await summarizer.generate_summary(messages)
        if len(summary) > 4096:
            summary = summary[:4093] + "..."
        notice = f"\n\n⏳ 此總結將在 {config.SUMMARY_AUTO_DELETE_SECONDS} 秒後自動刪除。"
        delivered = await _deliver(processing, message, summary + notice)
        if delivered is None:
            cache.release_summary_slot(chat.id)
            return
        await asyncio.sleep(config.SUMMARY_AUTO_DELETE_SECONDS)
        try:
            await context.bot.delete_message(chat_id=chat.id, message_id=delivered.message_id)
        except Exception:
            logger.error("Failed to auto-delete summary %s in chat %s",
                         delivered.message_id, chat.id, exc_info=True)
    except summarizer.SummaryError as e:
        cache.release_summary_slot(chat.id)
        await _deliver(processing, message, e.user_message)
    except Exception:
        logger.error("Unexpected error during /summarize in chat %s", chat.id, exc_info=True)
        cache.release_summary_slot(chat.id)
        await _deliver(processing, message, ERROR_TEXT)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error("Unhandled exception while processing update %s", update, exc_info=context.error)
