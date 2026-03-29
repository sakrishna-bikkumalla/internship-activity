import asyncio
import threading

import aiohttp
import nest_asyncio

nest_asyncio.apply()


class MockClient:
    def __init__(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        self._session = None

    def _run_loop(self):
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    async def _get_session(self):
        # Session MUST be created in the same loop it will be used in.
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def run_sync(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    async def request(self):
        async def _internal():
            session = await self._get_session()
            async with session.request("GET", "https://code.swecha.org/api/v4/users", timeout=10) as resp:
                return await resp.json()

        # Wrapping in an explicit task sometimes helps with contextvars
        # and other state that aiohttp/asyncio.timeout might rely on.
        task = asyncio.create_task(_internal())
        return await task


client = MockClient()
try:
    print(client.run_sync(client.request()))
except Exception as e:
    import traceback

    print(f"ERROR: {e}")
    traceback.print_exc()
