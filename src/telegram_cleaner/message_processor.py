from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING

logger = logging.getLogger(__name__)

from telethon import TelegramClient
from telethon.tl.functions.messages import SendReactionRequest
from telethon.tl.types import Channel, Chat, Message, ReactionEmpty, User

from telegram_cleaner.actions import Action
from telegram_cleaner.ai_agent import AIAgent, AIConfig, AIProvider
from telegram_cleaner.error_handlers import retry_on_flood_wait
from telegram_cleaner import constants

if TYPE_CHECKING:
    from telegram_cleaner.constants import ChatEntity
    from telegram_cleaner.export import ExportBuffer


class MessageProcessor(ABC):
    def __init__(
        self,
        client: TelegramClient,
        chat: ChatEntity,
        action: Action,
        cache: dict,
        me,
        simultaneous_processors,
        export_buffer: ExportBuffer | None = None,
    ):
        self.client = client
        self.chat = chat
        self.action = action
        self.export_buffer = export_buffer
        self.cache = cache
        self.me = me
        self.simultaneous_processors = simultaneous_processors

    @cached_property
    def wait_time(self):
        return constants.SAFE_TELEGRAM_WAIT_TIME * self.simultaneous_processors

    async def process(self, msg: Message) -> bool:
        to_continue = True
        if self.stop_condition:
            to_continue = False
        self.cache[self.action.value][self.chat.id].append(msg)
        if self.export_buffer:
            self.export_buffer.add(action=self.action, chat=self.chat, msg=msg)
            if self.export_buffer.flush_needed():
                self.export_buffer.flush()
        return to_continue

    async def finalize(self) -> None:
        if self.export_buffer:
            self.export_buffer.flush()

    @property
    def cached(self):
        for key in chain((self.action.value,), self.alternative_cache_keys):
            if self.cache.get(key, {}).get(self.chat.id):
                return True
        return False

    def _iter_from_cache(self):
        cached = []
        for key in chain((self.action.value,), self.alternative_cache_keys):
            cached_messages = self.cache.get(key, {}).get(self.chat.id, [])
            if cached_messages:
                cached.append(cached_messages)
        if cached:
            for msg in cached[0]:
                yield msg

    @property
    def alternative_cache_keys(self) -> tuple:
        return ()

    @property
    @abstractmethod
    def async_messages_iterator(self) -> any: ...

    @property
    @abstractmethod
    def stop_condition(self) -> any: ...

    @property
    @abstractmethod
    def export_buffer_needed(self) -> bool: ...


class ExportReactionsProcessor(MessageProcessor):
    async def process(self, msg: Message):
        to_continue = True
        if msg.reactions and any(
            [reaction.chosen_order is not None for reaction in msg.reactions.results]
        ):
            to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        ...
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, wait_time=self.wait_time)

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return True


class ExportMessagesProcessor(MessageProcessor):
    async def process(self, msg: Message):
        to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        ...
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, from_user=self.me.id, wait_time=self.wait_time)

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return True


class RemoveReactionsProcessor(MessageProcessor):
    async def process(self, msg):
        to_continue = True
        if msg.reactions and any(
            [reaction.chosen_order is not None for reaction in msg.reactions.results]
        ):
            await retry_on_flood_wait(
                self.client,
                SendReactionRequest(
                    peer=self.chat, msg_id=msg.id, reaction=[ReactionEmpty()]
                )
            )
            to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        ...
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, wait_time=self.wait_time)

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return False

    @property
    def alternative_cache_keys(self) -> tuple:
        return (Action.EXPORT_REACTIONS.value,)


class RemoveMessagesProcessor(MessageProcessor):
    async def process(self, msg):
        to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        message_ids = [msg.id for msg in self.cache[self.action.value][self.chat.id]]
        chunk_size = 100
        for i in range(0, len(message_ids), chunk_size):
            chunk = message_ids[i : i + chunk_size]
            await retry_on_flood_wait(
                self.client.delete_messages,
                entity=self.chat, message_ids=chunk, revoke=True
            )
        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, from_user=self.me.id, wait_time=self.wait_time)

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return False

    @property
    def alternative_cache_keys(self) -> tuple:
        return (Action.EXPORT_MESSAGES.value,)


class LeaveGroupProcessor(MessageProcessor):
    async def finalize(self) -> None:
        if isinstance(self.chat, (Channel, Chat)):
            await retry_on_flood_wait(
                self.client.delete_dialog, entity=self.chat, revoke=False
            )

        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, wait_time=self.wait_time)

    @property
    def stop_condition(self) -> any:
        return True

    @property
    def export_buffer_needed(self) -> bool:
        return False


class DeleteChatForBothProcessor(MessageProcessor):
    async def finalize(self) -> None:
        if isinstance(self.chat, User):
            message_ids = [
                msg.id for msg in self.cache[self.action.value][self.chat.id]
            ]
            await retry_on_flood_wait(
                self.client.delete_messages,
                entity=self.chat, message_ids=message_ids, revoke=True
            )
            await retry_on_flood_wait(
                self.client.delete_dialog, entity=self.chat, revoke=True
            )
        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return (
            self._iter_from_cache()
            if self.cached
            else self.client.iter_messages(entity=self.chat.id, wait_time=self.wait_time)
        )

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return False


class DeleteChatOnlyForMeProcessor(MessageProcessor):
    async def finalize(self) -> None:
        if isinstance(self.chat, User):
            message_ids = [
                msg.id for msg in self.cache[self.action.value][self.chat.id]
            ]
            await retry_on_flood_wait(
                self.client.delete_messages, entity=self.chat, message_ids=message_ids, revoke=False
            )
            await retry_on_flood_wait(
                self.client.delete_dialog, entity=self.chat, revoke=False
            )
        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return (
            self._iter_from_cache()
            if self.cached
            else self.client.iter_messages(entity=self.chat.id, wait_time=self.wait_time)
        )

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return False


class BaseAIAnalyzeProcessor(MessageProcessor, ABC):
    """Base processor for AI-powered analysis of messages.

    Collects messages during iteration and analyzes them in batches
    during finalize() to reduce LLM API costs.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ai_agent: AIAgent | None = None
        self._violation_message_ids: list[int] = []
        # Buffer for batch analysis: list of (message_id, analysis_text)
        self._pending_messages: list[tuple[int, str]] = []

    def _init_ai_agent(self, config) -> None:
        """Initialize AI agent from config."""
        ai_config = AIConfig(
            provider=AIProvider(config.AI_PROVIDER),
            ollama_url=config.OLLAMA_URL,
            ollama_model=config.OLLAMA_MODEL,
            openai_api_key=config.OPENAI_API_KEY,
            openai_model=config.OPENAI_MODEL,
            openai_base_url=config.OPENAI_BASE_URL,
            batch_size=config.AI_BATCH_SIZE,
            ai_debug=config.AI_DEBUG,
        )
        self._ai_agent = AIAgent(config=ai_config)

    @property
    @abstractmethod
    def include_media(self) -> bool:
        """Whether to include media messages (photo, video, audio) in analysis."""
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(
            entity=self.chat.id,
            from_user=self.me.id,
            wait_time=self.wait_time,
        )

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return False

    def _get_message_text(self, msg: Message) -> str:
        """Extract text from a message, including caption for media."""
        # msg.message contains both the text and the media caption in Telethon
        return (msg.message or "").strip()

    def _has_media(self, msg: Message) -> bool:
        """Check if message has media content."""
        return bool(msg.media)

    async def _run_batch_analysis(self) -> None:
        """Run batch analysis on all pending messages."""
        if not self._pending_messages:
            logger.debug("No pending messages for batch analysis")
            return

        msg_ids = [mid for mid, _ in self._pending_messages]
        logger.debug(
            "Starting batch analysis: %d messages, ids=%s",
            len(self._pending_messages),
            msg_ids[:10],
        )
        if len(msg_ids) > 10:
            logger.debug("... and %d more messages", len(msg_ids) - 10)

        texts = [text for _, text in self._pending_messages]
        results = await self._ai_agent.analyze_batch(texts)

        violations_found = 0
        for (msg_id, _), result in zip(self._pending_messages, results):
            if result.is_violation:
                self._violation_message_ids.append(msg_id)
                violations_found += 1
                logger.debug(
                    "VIOLATION DETECTED: msg_id=%s, articles=%s, confidence=%.2f, reason=%s",
                    msg_id,
                    result.articles,
                    result.confidence,
                    result.reason,
                )

        logger.debug(
            "Batch analysis completed: %d processed, %d violations found",
            len(self._pending_messages),
            violations_found,
        )

        self._pending_messages.clear()


class AIAnalyzeTextProcessor(BaseAIAnalyzeProcessor):
    """Analyze only text messages for legal violations."""

    @property
    def include_media(self) -> bool:
        return False

    async def process(self, msg: Message) -> bool:
        text = self._get_message_text(msg)
        if not text:
            logger.debug("Skipping empty text message: msg_id=%s", msg.id)
            return True  # skip empty messages

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered text message for AI analysis: msg_id=%s, text_len=%d, text_preview=%s",
            msg.id,
            len(text),
            text[:100],
        )

        return True

    async def finalize(self) -> None:
        if self._ai_agent is None:
            self._init_ai_agent(self._get_config())
        await self._run_batch_analysis()
        await super().finalize()

    def _get_config(self):
        """Get config from the cleaner context."""
        from telegram_cleaner.config import Config
        return Config.load()


class AIAnalyzeAllProcessor(BaseAIAnalyzeProcessor):
    """Analyze text and media messages for legal violations."""

    @property
    def include_media(self) -> bool:
        return True

    async def process(self, msg: Message) -> bool:
        text = self._get_message_text(msg)
        if not text and not self._has_media(msg):
            logger.debug("Skipping empty message (no text, no media): msg_id=%s", msg.id)
            return True  # skip empty messages

        # For media messages, include media type info in analysis
        analysis_text = text
        if self._has_media(msg) and not analysis_text:
            # If only media without text, we still note it
            analysis_text = f"[медиа-сообщение: {self._get_media_type(msg)}]"

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, analysis_text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered message for AI analysis: msg_id=%s, has_media=%s, text_len=%d, text_preview=%s",
            msg.id,
            self._has_media(msg),
            len(analysis_text),
            analysis_text[:100],
        )

        return True

    def _get_media_type(self, msg: Message) -> str:
        """Get human-readable media type."""
        if msg.photo:
            return "фото"
        if msg.video or msg.video_note:
            return "видео/кружок"
        if msg.voice or msg.audio:
            return "аудио"
        if msg.document:
            return "документ"
        return "медиа"

    async def finalize(self) -> None:
        if self._ai_agent is None:
            self._init_ai_agent(self._get_config())
        await self._run_batch_analysis()
        await super().finalize()

    def _get_config(self):
        from telegram_cleaner.config import Config
        return Config.load()


class BaseAIAnalyzeAndDeleteProcessor(BaseAIAnalyzeProcessor, ABC):
    """Base processor for AI analysis + deletion of violating messages.

    Iterates ALL messages in the chat (not just the user's own messages).
    During iteration:
    - All messages are stored in _all_messages for related-message lookup.
    - Only the user's own messages are added to _pending_messages for AI analysis.

    During finalize():
    1. Run AI analysis on the user's pending messages.
    2. For each violating message (user's own), collect related messages:
       - Messages that reply to the violating message (unconditional — always deleted)
       - Messages that are replied to by the violating message (unconditional)
       - All messages within AI_RELATED_MINUTES time window around the violation
    3. Delete all collected messages (violating + related), regardless of author.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Store all messages by id for related message lookup
        self._all_messages: dict[int, Message] = {}
        # Related message ids to delete (in addition to violations)
        self._related_message_ids: set[int] = set()

    @property
    def async_messages_iterator(self) -> any:
        """Iterate ALL messages in the chat (not just user's own).
        
        We need all messages to find related messages (replies, time window)
        that may belong to other users.
        """
        return self.client.iter_messages(
            entity=self.chat.id,
            wait_time=self.wait_time,
        )

    async def process(self, msg: Message) -> bool:
        # Store ALL messages for later related-message lookup
        self._all_messages[msg.id] = msg
        return True

    async def finalize(self) -> None:
        if self._ai_agent is None:
            self._init_ai_agent(self._get_config())

        # Run batch analysis on all pending messages (user's own messages only)
        await self._run_batch_analysis()

        logger.debug(
            "AI analysis complete: %d violations found out of %d pending messages",
            len(self._violation_message_ids),
            len(self._pending_messages) + len(self._violation_message_ids),
        )

        # Collect related messages for each violation
        related_minutes = self._get_related_minutes()
        for violation_id in self._violation_message_ids:
            violation_msg = self._all_messages.get(violation_id)
            if violation_msg is None:
                continue

            violation_date = violation_msg.date
            if violation_date is None:
                continue

            # Ensure violation_date is timezone-aware
            if violation_date.tzinfo is None:
                violation_date = violation_date.replace(tzinfo=timezone.utc)

            time_window = timedelta(minutes=related_minutes)

            for msg_id, msg in self._all_messages.items():
                if msg_id in self._related_message_ids or msg_id in self._violation_message_ids:
                    continue

                msg_date = msg.date
                if msg_date is None:
                    continue

                # Ensure msg_date is timezone-aware
                if msg_date.tzinfo is None:
                    msg_date = msg_date.replace(tzinfo=timezone.utc)

                # 1. Messages that reply to the violating message (unconditional)
                if msg.reply_to and msg.reply_to.reply_to_msg_id == violation_id:
                    self._related_message_ids.add(msg_id)
                    continue

                # 2. Messages that are replied to by the violating message (unconditional)
                if violation_msg.reply_to and violation_msg.reply_to.reply_to_msg_id == msg_id:
                    self._related_message_ids.add(msg_id)
                    continue

                # 3. All messages within the time window around the violation
                time_diff = abs(msg_date - violation_date)
                if time_diff <= time_window:
                    self._related_message_ids.add(msg_id)
                    continue

        # Combine violation and related message ids
        all_to_delete = set(self._violation_message_ids) | self._related_message_ids

        logger.debug(
            "Collected %d related messages for %d violations, total to delete: %d",
            len(self._related_message_ids),
            len(self._violation_message_ids),
            len(all_to_delete),
        )

        # Delete all collected messages (revoke=True = delete for everyone)
        if all_to_delete:
            chunk_size = 100
            ids_list = sorted(all_to_delete)
            logger.debug("Deleting %d messages in chunks of %d", len(ids_list), chunk_size)
            for i in range(0, len(ids_list), chunk_size):
                chunk = ids_list[i : i + chunk_size]
                logger.debug("Deleting chunk: ids=%s", chunk)
                await retry_on_flood_wait(
                    self.client.delete_messages,
                    entity=self.chat,
                    message_ids=chunk,
                    revoke=True,
                )
            logger.debug("Successfully deleted all %d messages", len(ids_list))
        else:
            logger.debug("No messages to delete")

    def _get_related_minutes(self) -> int:
        """Get the time window in minutes for related messages."""
        from telegram_cleaner.config import Config
        config = Config.load()
        return config.AI_RELATED_MINUTES

    def _get_config(self):
        from telegram_cleaner.config import Config
        return Config.load()


class AIAnalyzeAndDeleteTextProcessor(BaseAIAnalyzeAndDeleteProcessor):
    """Analyze text messages and delete violating ones (for everyone)
    along with related messages (replies, and messages within the time window).

    Iterates ALL messages in the chat. Only the user's own text messages
    are analyzed by AI. Related messages (replies, time window) of ANY author
    are deleted along with violations.
    """

    @property
    def include_media(self) -> bool:
        return False

    async def process(self, msg: Message) -> bool:
        # Always store in _all_messages via super() first
        await super().process(msg)

        text = self._get_message_text(msg)
        if not text:
            logger.debug("Skipping empty text message (delete mode): msg_id=%s", msg.id)
            return True

        # Only analyze user's own messages
        if msg.sender_id != self.me.id:
            logger.debug("Skipping other user's message (delete mode): msg_id=%s, sender=%s", msg.id, msg.sender_id)
            return True

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered own text message for AI analysis + delete: msg_id=%s, text_len=%d, text_preview=%s",
            msg.id,
            len(text),
            text[:100],
        )

        return True


class AIAnalyzeAndDeleteAllProcessor(BaseAIAnalyzeAndDeleteProcessor):
    """Analyze text and media messages and delete violating ones (for everyone)
    along with related messages (replies, and messages within the time window).

    Iterates ALL messages in the chat. Only the user's own messages
    are analyzed by AI. Related messages (replies, time window) of ANY author
    are deleted along with violations.
    """

    @property
    def include_media(self) -> bool:
        return True

    async def process(self, msg: Message) -> bool:
        # Always store in _all_messages via super() first
        await super().process(msg)

        text = self._get_message_text(msg)
        if not text and not self._has_media(msg):
            logger.debug("Skipping empty message (delete mode, all): msg_id=%s", msg.id)
            return True

        # Only analyze user's own messages
        if msg.sender_id != self.me.id:
            logger.debug("Skipping other user's message (delete mode, all): msg_id=%s, sender=%s", msg.id, msg.sender_id)
            return True

        analysis_text = text
        if self._has_media(msg) and not analysis_text:
            analysis_text = f"[медиа-сообщение: {self._get_media_type(msg)}]"

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, analysis_text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered own message for AI analysis + delete: msg_id=%s, has_media=%s, text_len=%d, text_preview=%s",
            msg.id,
            self._has_media(msg),
            len(analysis_text),
            analysis_text[:100],
        )

        return True

    def _get_media_type(self, msg: Message) -> str:
        if msg.photo:
            return "фото"
        if msg.video or msg.video_note:
            return "видео/кружок"
        if msg.voice or msg.audio:
            return "аудио"
        if msg.document:
            return "документ"
        return "медиа"


class BaseAIAnalyzeAndDeleteWithRelatedProcessor(BaseAIAnalyzeAndDeleteProcessor, ABC):
    """Base processor for AI analysis + deletion of violating messages
    along with related messages.

    NOTE: This class is kept for backward compatibility.
    The related-messages logic has been merged into BaseAIAnalyzeAndDeleteProcessor,
    so all delete processors now collect related messages by default.
    This class behaves identically to BaseAIAnalyzeAndDeleteProcessor.
    """

    pass


class AIAnalyzeAndDeleteWithRelatedTextProcessor(BaseAIAnalyzeAndDeleteWithRelatedProcessor):
    """Analyze text messages, delete violating ones along with related messages.

    NOTE: This class is kept for backward compatibility.
    The related-messages logic is now built into all delete processors.
    """

    @property
    def include_media(self) -> bool:
        return False

    async def process(self, msg: Message) -> bool:
        # Always store in _all_messages via super() first
        await super().process(msg)

        text = self._get_message_text(msg)
        if not text:
            logger.debug("Skipping empty text message (delete+related mode): msg_id=%s", msg.id)
            return True

        # Only analyze user's own messages
        if msg.sender_id != self.me.id:
            logger.debug("Skipping other user's message (delete+related mode): msg_id=%s, sender=%s", msg.id, msg.sender_id)
            return True

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered own text message for AI analysis + delete+related: msg_id=%s, text_len=%d, text_preview=%s",
            msg.id,
            len(text),
            text[:100],
        )

        return True


class AIAnalyzeAndDeleteWithRelatedAllProcessor(BaseAIAnalyzeAndDeleteWithRelatedProcessor):
    """Analyze text and media messages, delete violating ones along with related messages.

    NOTE: This class is kept for backward compatibility.
    The related-messages logic is now built into all delete processors.
    """

    @property
    def include_media(self) -> bool:
        return True

    async def process(self, msg: Message) -> bool:
        # Always store in _all_messages via super() first
        await super().process(msg)

        text = self._get_message_text(msg)
        if not text and not self._has_media(msg):
            logger.debug("Skipping empty message (delete+related mode, all): msg_id=%s", msg.id)
            return True

        # Only analyze user's own messages
        if msg.sender_id != self.me.id:
            logger.debug("Skipping other user's message (delete+related mode, all): msg_id=%s, sender=%s", msg.id, msg.sender_id)
            return True

        analysis_text = text
        if self._has_media(msg) and not analysis_text:
            analysis_text = f"[медиа-сообщение: {self._get_media_type(msg)}]"

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, analysis_text))
        self.cache[self.action.value][self.chat.id].append(msg)

        logger.debug(
            "Buffered own message for AI analysis + delete+related: msg_id=%s, has_media=%s, text_len=%d, text_preview=%s",
            msg.id,
            self._has_media(msg),
            len(analysis_text),
            analysis_text[:100],
        )

        return True

    def _get_media_type(self, msg: Message) -> str:
        if msg.photo:
            return "фото"
        if msg.video or msg.video_note:
            return "видео/кружок"
        if msg.voice or msg.audio:
            return "аудио"
        if msg.document:
            return "документ"
        return "медиа"
