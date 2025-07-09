import asyncio
from collections import defaultdict
from functools import partial

from rich.console import Console
from telethon import TelegramClient

from telegram_cleaner.cleaner import Cleaner
from telegram_cleaner.config import Config
from telegram_cleaner.export import ExportBuffer
from telegram_cleaner.logging_setup import logging_configure
from telegram_cleaner.translations import Translator
from telegram_cleaner.ui import TerminalUI

logging_configure()


async def main() -> None:
    config = Config.load()
    terminal_ui = TerminalUI(console=Console(), translator=Translator(config.LANG))
    client = TelegramClient(
        session="cleaner_session",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        app_version="1.2.3",
        device_model="PC",
        system_version="Linux"
    )
    export_buffer = ExportBuffer()
    cache = defaultdict(partial(defaultdict, list))
    async with Cleaner(
        config=config, terminal_ui=terminal_ui, client=client,
    ) as cleaner:
        await cleaner.run(export_buffer=export_buffer, cache=cache)


if __name__ == "__main__":
    asyncio.run(main())
