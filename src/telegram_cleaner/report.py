"""Report generator for AI-deleted messages.

Creates and appends to a report file in the `report/` directory
each time messages are deleted by AI analysis.

The report file name includes the start timestamp of the process,
so each user session creates its own file that grows incrementally
as deletions happen.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from telethon.tl.types import Message

logger = logging.getLogger(__name__)

REPORT_DIR = Path("report")

# Lazy-initialised: set on first call to write_deletion_report()
_REPORT_FILE: Path | None = None


def _get_report_file() -> Path:
    """Return the report file path, initialising it with a timestamp on first call."""
    global _REPORT_FILE
    if _REPORT_FILE is None:
        REPORT_DIR.mkdir(exist_ok=True)
        start_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        _REPORT_FILE = REPORT_DIR / f"ai_deletion_report_{start_ts}.txt"
        logger.info("Deletion report file: %s", _REPORT_FILE)
    return _REPORT_FILE


def write_deletion_report(
    messages: list[Message],
    articles: list[str],
    reason: str,
    chat_title: str,
    chat_id: int,
) -> None:
    """Append a deletion report entry for a batch of deleted messages.

    The report file is created on first call with a timestamp in its name,
    and new entries are appended to it within the same process session.

    Args:
        messages: List of deleted Message objects.
        articles: List of violated articles (e.g. ["Ст. 280.3 УК РФ"]).
        reason: Short description of the violation reason.
        chat_title: Display name of the chat.
        chat_id: Telegram chat ID.
    """
    report_file = _get_report_file()

    now = datetime.now(timezone.utc).astimezone()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S %Z")

    articles_str = ", ".join(articles) if articles else "не указаны"

    lines: list[str] = []
    lines.append("=" * 72)
    lines.append(f"Время удаления: {timestamp}")
    lines.append(f"Чат: {chat_title} (id={chat_id})")
    lines.append(f"Причина: {reason}")
    lines.append(f"Статьи: {articles_str}")
    lines.append(f"Количество сообщений: {len(messages)}")
    lines.append("-" * 72)

    for msg in messages:
        msg_date = ""
        if msg.date:
            try:
                msg_date = msg.date.astimezone().strftime("%Y-%m-%d %H:%M:%S")
            except (OSError, ValueError):
                msg_date = str(msg.date)

        msg_text = (msg.message or "").strip().replace("\n", " ")
        # Truncate very long messages for readability
        if len(msg_text) > 500:
            msg_text = msg_text[:500] + "..."

        lines.append(f"  [{msg_date}] id={msg.id} | {msg_text}")

    lines.append("=" * 72)
    lines.append("")  # trailing newline

    report_text = "\n".join(lines)

    try:
        with open(report_file, "a", encoding="utf-8") as f:
            f.write(report_text + "\n")
        logger.info(
            "Deletion report appended to %s: %d messages deleted from '%s'",
            report_file,
            len(messages),
            chat_title,
        )
    except OSError as e:
        logger.error("Failed to write deletion report to %s: %s", report_file, e)