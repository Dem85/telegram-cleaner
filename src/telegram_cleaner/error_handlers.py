import asyncio

from telethon.errors import FloodWaitError


async def retry_on_flood_wait(coro, max_retries=10):
    """Retry on FloodWaitError"""
    for attempt in range(max_retries):
        try:
            return await coro
        except FloodWaitError as e:
            wait_time = e.seconds
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                raise
