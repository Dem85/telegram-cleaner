from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import chain
from typing import TYPE_CHECKING

from telethon.tl.functions.messages import SendReactionRequest
from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, Message, User, ReactionEmpty

from telegram_cleaner.actions import Action

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
        export_buffer: ExportBuffer | None = None,
    ):
        self.client = client
        self.chat = chat
        self.action = action
        self.export_buffer = export_buffer
        self.cache = cache
        self.me = me

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
        return self.client.iter_messages(entity=self.chat.id)

    @property
    def stop_condition(self) -> any:
        return False

    @property
    def export_buffer_needed(self) -> bool:
        return True


class ExportMessagesProcessor(MessageProcessor):
    async def process(self, msg: Message):
        to_continue = False
        if msg.from_id.user_id == self.me.id:
            to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        ...
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, from_user=self.me.id)

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
            await self.client(SendReactionRequest(
                peer=self.chat,
                msg_id=msg.id,
                reaction=[ReactionEmpty()]
            ))
            to_continue = await super().process(msg=msg)
        return to_continue

    async def finalize(self) -> None:
        ...
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id)

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
            await self.client.delete_messages(
                entity=self.chat, message_ids=chunk, revoke=True
            )
        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id, from_user=self.me.id)

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
            await self.client.delete_dialog(entity=self.chat, revoke=False)

        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return self.client.iter_messages(entity=self.chat.id)

    @property
    def stop_condition(self) -> any:
        return True

    @property
    def export_buffer_needed(self) -> bool:
        return False


class DeleteChatForBothProcessor(MessageProcessor):
    async def finalize(self) -> None:
        if isinstance(self.chat, User):
            await self.client.delete_dialog(entity=self.chat, revoke=True)
        await super().finalize()

    @property
    def async_messages_iterator(self) -> any:
        return (
            self._iter_from_cache()
            if self.cached
            else self.client.iter_messages(entity=self.chat.id)
        )

    @property
    def stop_condition(self) -> any:
        return True

    @property
    def export_buffer_needed(self) -> bool:
        return False


class DeleteChatOnlyForMeProcessor(MessageProcessor):
    async def finalize(self) -> None:
        if isinstance(self.chat, User):
            await self.client.delete_dialog(entity=self.chat, revoke=False)
        await super().finalize()
        ...

    @property
    def async_messages_iterator(self) -> any:
        return (
            self._iter_from_cache()
            if self.cached
            else self.client.iter_messages(entity=self.chat.id)
        )

    @property
    def stop_condition(self) -> any:
        return True

    @property
    def export_buffer_needed(self) -> bool:
        return False
