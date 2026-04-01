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
        if self._session is None:
            self._session = aiohttp.ClientSession()
        return self._session

    def run_sync(self, coro):
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result()

    async def request(self):
        session = await self._get_session()
        async with session.request("GET", "https://code.swecha.org/api/v4/users", timeout=10) as resp:
            return await resp.json()


client = MockClient()
try:
    print(client.run_sync(client.request()))
except Exception as e:
    print(f"REPRODUCED ERROR: {e}")
