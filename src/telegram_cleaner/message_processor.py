from __future__ import annotations

from abc import ABC, abstractmethod
from functools import cached_property
from itertools import chain
from typing import TYPE_CHECKING

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
            return

        texts = [text for _, text in self._pending_messages]
        results = await self._ai_agent.analyze_batch(texts)

        for (msg_id, _), result in zip(self._pending_messages, results):
            if result.is_violation:
                self._violation_message_ids.append(msg_id)

        self._pending_messages.clear()


class AIAnalyzeTextProcessor(BaseAIAnalyzeProcessor):
    """Analyze only text messages for legal violations."""

    @property
    def include_media(self) -> bool:
        return False

    async def process(self, msg: Message) -> bool:
        text = self._get_message_text(msg)
        if not text:
            return True  # skip empty messages

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, text))
        self.cache[self.action.value][self.chat.id].append(msg)

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
            return True  # skip empty messages

        # For media messages, include media type info in analysis
        analysis_text = text
        if self._has_media(msg) and not analysis_text:
            # If only media without text, we still note it
            analysis_text = f"[медиа-сообщение: {self._get_media_type(msg)}]"

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, analysis_text))
        self.cache[self.action.value][self.chat.id].append(msg)

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
    """Base processor for AI analysis + deletion of violating messages."""

    async def finalize(self) -> None:
        if self._ai_agent is None:
            self._init_ai_agent(self._get_config())

        # Run batch analysis on all pending messages
        await self._run_batch_analysis()

        # First, collect all messages
        await super().finalize()

        # Delete violating messages (revoke=True = delete for everyone)
        if self._violation_message_ids:
            chunk_size = 100
            for i in range(0, len(self._violation_message_ids), chunk_size):
                chunk = self._violation_message_ids[i : i + chunk_size]
                await retry_on_flood_wait(
                    self.client.delete_messages,
                    entity=self.chat,
                    message_ids=chunk,
                    revoke=True,
                )

    def _get_config(self):
        from telegram_cleaner.config import Config
        return Config.load()


class AIAnalyzeAndDeleteTextProcessor(BaseAIAnalyzeAndDeleteProcessor):
    """Analyze text messages and delete violating ones (for everyone)."""

    @property
    def include_media(self) -> bool:
        return False

    async def process(self, msg: Message) -> bool:
        text = self._get_message_text(msg)
        if not text:
            return True

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, text))
        self.cache[self.action.value][self.chat.id].append(msg)

        return True


class AIAnalyzeAndDeleteAllProcessor(BaseAIAnalyzeAndDeleteProcessor):
    """Analyze text and media messages and delete violating ones (for everyone)."""

    @property
    def include_media(self) -> bool:
        return True

    async def process(self, msg: Message) -> bool:
        text = self._get_message_text(msg)
        if not text and not self._has_media(msg):
            return True

        analysis_text = text
        if self._has_media(msg) and not analysis_text:
            analysis_text = f"[медиа-сообщение: {self._get_media_type(msg)}]"

        # Buffer the message for batch analysis
        self._pending_messages.append((msg.id, analysis_text))
        self.cache[self.action.value][self.chat.id].append(msg)

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
