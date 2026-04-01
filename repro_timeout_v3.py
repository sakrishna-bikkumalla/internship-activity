import asyncio
import threading

import aiohttp


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

        # Explicitly wrapping in a task inside the loop
        async def _do():
            async with session.request("GET", "https://code.swecha.org/api/v4/users", timeout=10) as resp:
                return await resp.json()

        # We need to make sure this is called from the loop thread if we use create_task
        # but run_sync calls this coro in the loop thread already.
        return await _do()


client = MockClient()
try:
    # We pass the coroutine object to run_sync
    print(client.run_sync(client.request()))
except Exception as e:
    import traceback

    print(f"ERROR: {e}")
    traceback.print_exc()
