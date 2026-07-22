import asyncio

from telethon import TelegramClient
from telethon.tl.types import Channel, Chat, User

from telegram_cleaner import constants
from telegram_cleaner.actions import Action, get_available_actions
from telegram_cleaner.ai_agent import AIAgent, AIConfig, AIProvider
from telegram_cleaner.config import Config
from telegram_cleaner.constants import ChatEntity
from telegram_cleaner.error_handlers import retry_on_flood_wait
from telegram_cleaner.export import ExportBuffer
from telegram_cleaner.message_processor import MessageProcessor
from telegram_cleaner.ui import TerminalUI


AI_ACTIONS = {
    Action.AI_ANALYZE_TEXT,
    Action.AI_ANALYZE_ALL,
    Action.AI_ANALYZE_AND_DELETE_TEXT,
    Action.AI_ANALYZE_AND_DELETE_ALL,
    Action.AI_ANALYZE_AND_DELETE_WITH_RELATED_TEXT,
    Action.AI_ANALYZE_AND_DELETE_WITH_RELATED_ALL,
}


class Cleaner:
    def __init__(
        self, config: Config, terminal_ui: TerminalUI, client: TelegramClient,
    ) -> None:
        self.config = config
        self.terminal_ui = terminal_ui
        self.client = client
        self._ai_agent: AIAgent | None = None

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

        if len(picked_chats) < self.config.SIMULTANEOUS_PROCESSORS:
            simultaneous_processors = len(picked_chats)
        else:
            simultaneous_processors = self.config.SIMULTANEOUS_PROCESSORS

        await self._process_chats(
            simultaneous_processors=simultaneous_processors,
            picked_chats=picked_chats,
            picked_actions=picked_actions,
            export_buffer=export_buffer,
            cache=cache,
        )

        self.terminal_ui.show_completed()

    def _get_ai_agent(self) -> AIAgent:
        """Lazy initialization of AI agent (only when AI actions are selected)."""
        if self._ai_agent is None:
            ai_config = AIConfig(
                provider=AIProvider(self.config.AI_PROVIDER),
                ollama_url=self.config.OLLAMA_URL,
                ollama_model=self.config.OLLAMA_MODEL,
                openai_api_key=self.config.OPENAI_API_KEY,
                openai_model=self.config.OPENAI_MODEL,
                openai_base_url=self.config.OPENAI_BASE_URL,
                batch_size=self.config.AI_BATCH_SIZE,
                timeout=self.config.AI_TIMEOUT,
                ai_debug=self.config.AI_DEBUG,
            )
            self._ai_agent = AIAgent(config=ai_config)
        return self._ai_agent

    async def process_actions_with_semaphore(
        self, *, picked_chat, picked_actions, semaphore, export_buffer, progress, cache, simultaneous_processors,
    ) -> None:
        for picked_action in picked_actions:
            async with semaphore:
                me = await retry_on_flood_wait(self.client.get_me)
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
                    simultaneous_processors=simultaneous_processors,
                )
                # Inject AI agent into AI processors (lazy init)
                if picked_action in AI_ACTIONS:
                    processor._ai_agent = self._get_ai_agent()
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
                        simultaneous_processors=simultaneous_processors,
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
