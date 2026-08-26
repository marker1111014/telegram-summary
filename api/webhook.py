"""Vercel serverless entry point: Telegram webhook receiver."""
import asyncio
import hmac
import logging
import os
import sys

# Ensure project root is importable when Vercel bundles api/.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from telegram import Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot_core import config, handlers

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

application: Application = (
    ApplicationBuilder()
    .token(config.TELEGRAM_BOT_TOKEN)
    .updater(None)
    .build()
)
application.add_handler(CommandHandler(["start", "help"], handlers.start_command))
application.add_handler(CommandHandler("summarize", handlers.summarize_command))
application.add_handler(MessageHandler(
    filters.TEXT & ~filters.COMMAND & filters.ChatType.GROUPS & ~filters.VIA_BOT,
    handlers.handle_message,
))
application.add_error_handler(handlers.error_handler)

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

_initialized = False
_start_lock = asyncio.Lock()


async def _ensure_started() -> None:
    global _initialized
    if _initialized:
        return
    async with _start_lock:
        if not _initialized:
            await application.initialize()
            await application.start()
            _initialized = True
            logger.info("Telegram application initialized")


@app.post("/api/webhook")
async def telegram_webhook(request: Request) -> JSONResponse:
    secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if not hmac.compare_digest(secret.encode(), config.WEBHOOK_SECRET.encode()):
        return JSONResponse(status_code=403, content={"ok": False})

    try:
        payload = await request.json()
    except Exception:
        logger.warning("Discarding unparseable webhook body.")
        return JSONResponse(content={"ok": False})
    await _ensure_started()
    update = Update.de_json(payload, application.bot)
    if update is not None:
        try:
            await application.process_update(update)
        except Exception:
            logger.error("Error processing update %s", payload.get("update_id"), exc_info=True)
    return JSONResponse(content={"ok": True})
