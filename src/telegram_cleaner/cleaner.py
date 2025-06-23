import asyncio

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from telegram_cleaner import constants
from telegram_cleaner.actions import get_available_actions
from telegram_cleaner.config import Config
from telegram_cleaner.constants import ChatEntity
from telegram_cleaner.export import ExportBuffer
from telegram_cleaner.message_processor import MessageProcessor
from telegram_cleaner.ui import TerminalUI


class Cleaner:
    def __init__(
        self, config: Config, terminal_ui: TerminalUI, client: TelegramClient
    ) -> None:
        self.config = config
        self.terminal_ui = terminal_ui
        self.client = client

    async def run(self, export_buffer: ExportBuffer, cache: dict) -> None:
        self.terminal_ui.show_title()
        chats = await self._get_chats()
        picked_chats = self.terminal_ui.pick_chats(chats=chats)
        if not picked_chats:
            return
        available_actions = get_available_actions(chats=picked_chats)
        picked_actions = self.terminal_ui.pick_actions(
            available_actions=available_actions
        )
        if not picked_actions:
            return
        confirmation = self.terminal_ui.show_resume_info_and_continue(
            picked_chats=picked_chats, picked_actions=picked_actions
        )
        if not confirmation:
            return

        await self._process_chats(
            simultaneous_processors=self.config.SIMULTANEOUS_PROCESSORS,
            picked_chats=picked_chats,
            picked_actions=picked_actions,
            export_buffer=export_buffer,
            cache=cache,
        )

        self.terminal_ui.show_completed()

    async def process_actions_with_semaphore(
        self, *, picked_chat, picked_actions, semaphore, export_buffer, progress, cache
    ) -> None:
        for picked_action in picked_actions:
            async with semaphore:
                me = await self.client.get_me()
                processor_class = constants.ACTION_PROCESSOR_MAPPING.get(picked_action)
                processor: MessageProcessor = processor_class(
                    export_buffer=(
                        export_buffer if processor_class.export_buffer_needed else None
                    ),
                    client=self.client,
                    chat=picked_chat,
                    action=picked_action,
                    cache=cache,
                    me=me,
                )
                await self.terminal_ui.scan(processor=processor, progress=progress)

    async def _process_chats(
        self,
        simultaneous_processors,
        picked_chats,
        picked_actions,
        export_buffer,
        cache: dict,
    ) -> None:
        semaphore = asyncio.Semaphore(simultaneous_processors)
        async with self.terminal_ui.progress_context_manager() as progress:
            await asyncio.gather(
                *(
                    self.process_actions_with_semaphore(
                        picked_chat=chat,
                        picked_actions=picked_actions,
                        semaphore=semaphore,
                        export_buffer=export_buffer,
                        progress=progress,
                        cache=cache,
                    )
                    for chat in picked_chats
                )
            )

    async def _get_chats(self) -> list[ChatEntity]:
        result = []
        async for dialog in self.client.iter_dialogs():
            if isinstance(dialog.entity, Channel) and not dialog.is_group:
                continue
            elif isinstance(dialog.entity, (User, Chat, Channel)):
                result.append(dialog.entity)
        return result

    async def __aenter__(self):
        await self.client.start()
        return self

    async def __aexit__(self, *_):
        await self.client.disconnect()
