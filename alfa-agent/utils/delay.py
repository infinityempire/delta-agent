"""
Delay and scheduling utilities.
"""
import asyncio
import random


def get_random_delay_seconds(min_seconds: int = 7, max_seconds: int = 25) -> int:
    """
    Get a random delay between min and max values.
    
    Args:
        min_seconds: Minimum delay in seconds
        max_seconds: Maximum delay in seconds
        
    Returns:
        Delay in seconds
    """
    return random.randint(min_seconds, max_seconds)


async def async_random_delay(min_seconds: int = 7, max_seconds: int = 25) -> None:
    """
    Async version of random delay for use with asyncio.
    """
    delay = get_random_delay_seconds(min_seconds, max_seconds)
    await asyncio.sleep(delay)


def sync_random_delay(min_seconds: int = 7, max_seconds: int = 25) -> None:
    """
    Synchronous version of random delay using time.sleep.
    """
    import time
    delay = get_random_delay_seconds(min_seconds, max_seconds)
    time.sleep(delay)
