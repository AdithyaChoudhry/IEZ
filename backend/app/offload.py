"""
Keep the server responsive while a large upload is processed.

The service runs one event loop. An `async def` endpoint that parses a workbook inside it stops every other request (for
every user) until it finishes. `@off_main_loop` runs the whole endpoint in a worker thread instead: the same code, the same
errors, nothing rejected - only other requests keep being served meanwhile.
"""
import asyncio
import functools

from fastapi.concurrency import run_in_threadpool


def off_main_loop(endpoint):
    @functools.wraps(endpoint)                       # FastAPI reads the wrapped signature for the form fields
    async def wrapper(*args, **kwargs):
        return await run_in_threadpool(lambda: asyncio.run(endpoint(*args, **kwargs)))
    return wrapper
