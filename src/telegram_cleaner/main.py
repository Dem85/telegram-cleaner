import asyncio
from collections import defaultdict
from functools import partial

from rich.console import Console
from telethon import TelegramClient
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate

from telegram_cleaner.cleaner import Cleaner
from telegram_cleaner.config import Config
from telegram_cleaner.export import ExportBuffer
from telegram_cleaner.logging_setup import logging_configure
from telegram_cleaner.translations import Translator
from telegram_cleaner.ui import TerminalUI

logging_configure()


def _build_proxy(config: Config) -> tuple | None:
    """Build a proxy for Telethon if proxy is enabled.

    For ``socks5`` and ``http`` returns a standard tuple
    ``(type, host, port[, user, password])``.

    For ``mtproto`` returns ``(host, port, secret)`` tuple where
    ``secret`` is ``bytes`` decoded from the hex string stored in
    ``MTPROTO_SECRET`` config field.

    Returns ``None`` when proxy is disabled.
    """
    if not config.MTPROTO_ENABLED:
        return None
    proxy_type = config.MTPROTO_TYPE
    host = config.MTPROTO_HOST
    port = config.MTPROTO_PORT

    if proxy_type == "mtproto":
        secret = config.MTPROTO_SECRET
        if isinstance(secret, bytes):
            secret = secret.hex()
        else:
            secret = secret.removeprefix("0x")
        return (host, port, secret)

    user = config.MTPROTO_USER
    password = config.MTPROTO_PASS
    if user and password:
        return (proxy_type, host, port, user, password)
    return (proxy_type, host, port)


async def main() -> None:
    config = Config.load()
    terminal_ui = TerminalUI(console=Console(), translator=Translator(config.LANG))
    proxy = _build_proxy(config)

    # For MTProto proxy we need a special connection type
    use_mtproto = config.MTPROTO_ENABLED and config.MTPROTO_TYPE == "mtproto"

    client_kwargs = dict(
        session="cleaner_session",
        api_id=config.API_ID,
        api_hash=config.API_HASH,
        proxy=proxy,
        app_version="1.2.3",
        device_model="PC",
        system_version="Linux",
    )
    if use_mtproto:
        client_kwargs["connection"] = ConnectionTcpMTProxyRandomizedIntermediate

    client = TelegramClient(**client_kwargs)
    export_buffer = ExportBuffer()
    cache = defaultdict(partial(defaultdict, list))

    async with Cleaner(
        config=config, terminal_ui=terminal_ui, client=client,
    ) as cleaner:
        await cleaner.run(export_buffer=export_buffer, cache=cache)


if __name__ == "__main__":
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No running event loop — safe to use asyncio.run()
        asyncio.run(main())
    else:
        # Already running in an event loop (e.g. debugpy)
        loop.create_task(main())
