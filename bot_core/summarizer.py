"""Gemini-powered conversation summarization."""
import asyncio
import logging
from typing import List

import google.api_core.exceptions
import google.generativeai as genai
from google.generativeai.types import (
    BlockedPromptException,
    GenerationConfig,
    HarmBlockThreshold,
    HarmCategory,
)

from bot_core import config

logger = logging.getLogger(__name__)

genai.configure(api_key=config.GEMINI_API_KEY)

_SAFETY_SETTINGS = [
    {"category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_HARASSMENT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
    {"category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
     "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE},
]

_model = genai.GenerativeModel(model_name=config.GEMINI_MODEL_NAME, safety_settings=_SAFETY_SETTINGS)

PROMPT_TEMPLATE = """You are a helpful assistant that summarizes Telegram group conversations.
Write the summary in the dominant language of the conversation.
Provide a concise, topic-based summary of the following messages.
Focus on key discussion points, decisions made, questions asked, and action items.

Formatting rules:
- Organize content under bold topic headings prefixed with emoji
- Reference contributors by their Telegram username (@username) when mentioning what they said
- Emphasize important names and numbers with bold (*) or italic (_) markers
- Do not include message IDs

--- Conversation Start ---
{conversation}
--- Conversation End ---

Topic-based summary:"""


class SummaryError(Exception):
    """Summary generation failed. `user_message` is safe to show users."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


def format_messages_for_prompt(messages: List[dict]) -> str:
    lines = []
    for msg in messages:
        timestamp = msg.get("ts", "")
        name = msg.get("user_name") or "?"
        username = msg.get("username")
        text = msg.get("text") or ""
        label = f"@{username} ({name})" if username else name
        lines.append(f"[{timestamp} - {label}]: {text}")
    return "\n".join(lines)


def _raise_from_response(response) -> str:
    """Validate a Gemini response; return the extracted text or raise SummaryError."""
    candidates = getattr(response, "candidates", None)
    if not candidates:
        feedback = getattr(response, "prompt_feedback", None)
        block_reason = getattr(feedback, "block_reason", None)
        reason = getattr(block_reason, "name", str(block_reason))
        logger.warning("Summary blocked by API. Reason: %s", reason)
        raise SummaryError(f"❌ Summary generation was blocked ({reason}). Please try again later.")

    candidate = candidates[0]
    finish_reason = getattr(candidate, "finish_reason", None)
    finish_name = getattr(finish_reason, "name", None) or str(finish_reason)
    if finish_name == "SAFETY":
        logger.warning("Summary stopped for safety reasons.")
        raise SummaryError("❌ Summary generation stopped due to safety concerns about the conversation content.")

    try:
        text = response.text.strip()
    except (ValueError, AttributeError):
        logger.warning("Response had no usable text part.")
        raise SummaryError("❌ The AI returned empty content. Please try again later.")
    if not text:
        logger.warning("Summary text was empty after stripping.")
        raise SummaryError("❌ The AI returned an empty summary.")
    return text


async def generate_summary(messages: List[dict]) -> str:
    conversation = format_messages_for_prompt(messages)
    if len(conversation) > 32000:
        logger.warning("Conversation prompt is %d chars; may exceed model limits.", len(conversation))
    prompt = PROMPT_TEMPLATE.format(conversation=conversation)

    try:
        response = await asyncio.wait_for(
            asyncio.to_thread(
                _model.generate_content,
                prompt,
                generation_config=GenerationConfig(),
                request_options={"timeout": config.API_TIMEOUT_SECONDS},
            ),
            timeout=config.API_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        raise SummaryError(
            f"⏱️ The summarization request timed out after {config.API_TIMEOUT_SECONDS} seconds. Please try again later."
        )
    except google.api_core.exceptions.ResourceExhausted:
        raise SummaryError("❌ Rate limit reached on the AI service. Please try again later.")
    except BlockedPromptException as e:
        raise SummaryError(f"❌ Summary generation was blocked ({e}).")
    except google.api_core.exceptions.GoogleAPIError as e:
        logger.error("Gemini API error: %s", e, exc_info=True)
        raise SummaryError("❌ The AI service reported an error. Please try again later.")

    return _raise_from_response(response)
