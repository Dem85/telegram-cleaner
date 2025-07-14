import asyncio

from telethon.errors import FloodWaitError


async def retry_on_flood_wait(func, *args, **kwargs) -> any:
    """Retry on FloodWaitError"""
    max_retries = kwargs.get("max_retries", 10)
    for attempt in range(max_retries):
        try:
            return await func(*args, **kwargs)
        except FloodWaitError as e:
            wait_time = e.seconds
            if attempt < max_retries - 1:
                await asyncio.sleep(wait_time)
            else:
                raise
