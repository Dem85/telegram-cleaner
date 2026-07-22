import asyncio
import base64
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


def _is_hex(s: str) -> bool:
    """Check if a string is a valid hexadecimal string."""
    try:
        bytes.fromhex(s)
        return True
    except ValueError:
        return False


def _base64url_to_hex(s: str) -> str:
    """Convert a base64url-encoded string to a hex string.

    Telethon's ``normalize_secret`` tries ``bytes.fromhex()`` first,
    then falls back to ``base64.b64decode()``. However ``b64decode``
    does NOT support base64url (which uses ``-`` and ``_`` instead of
    ``+`` and ``/``). This function converts base64url to hex so that
    Telethon can always decode via ``fromhex()``.
    """
    # Add padding if needed
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    # Convert base64url -> standard base64
    s = s.replace("-", "+").replace("_", "/")
    decoded = base64.b64decode(s)
    return decoded.hex()


def _build_proxy(config: Config) -> tuple | None:
    """Build a proxy for Telethon if proxy is enabled.

    For ``socks5`` and ``http`` returns a standard tuple
    ``(type, host, port[, user, password])``.

    For ``mtproto`` returns ``(host, port, secret)`` tuple where
    ``secret`` is a hex string (Telethon's ``normalize_secret``
    decodes it internally).

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
        elif isinstance(secret, str):
            secret = secret.removeprefix("0x")
            # Telethon's normalize_secret() tries bytes.fromhex() first,
            # then falls back to base64.b64decode(). However b64decode
            # does NOT support base64url (which uses '-' and '_' instead
            # of '+' and '/'). Convert base64url to hex here so Telethon
            # can always decode via fromhex().
            if not _is_hex(secret):
                secret = _base64url_to_hex(secret)
        else:
            raise TypeError(
                f"MTPROTO_SECRET must be str or bytes, got {type(secret).__name__}"
            )
        # Telethon's normalize_secret() expects a hex string
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

    # Debug: log proxy status
    import logging
    log = logging.getLogger(__name__)
    log.info("MTPROTO_ENABLED=%s MTPROTO_TYPE=%s proxy=%s",
             config.MTPROTO_ENABLED, config.MTPROTO_TYPE, proxy)

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
