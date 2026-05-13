import asyncio
import logging
import threading
from typing import Any, Coroutine, Optional

logger = logging.getLogger(__name__)


class GlobalBridge:
    """
    A unified bridge to manage a single background event loop for the entire application.
    Prevents loop fragmentation and 'Timeout context manager' errors in multi-user environments.
    """

    _instance: Optional["GlobalBridge"] = None
    _lock = threading.Lock()
    _loop: asyncio.AbstractEventLoop
    _initialized: bool
    _thread: threading.Thread

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(GlobalBridge, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run_loop, name="GitLab-Global-Bridge", daemon=True)
        self._thread.start()
        self._initialized = True
        logger.info("GlobalBridge initialized with a dedicated background thread.")

    def _run_loop(self):
        """Thread target: Set the loop and run forever."""
        asyncio.set_event_loop(self._loop)
        # Ensure a default policy is set for this background thread
        try:
            asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
        except Exception:
            pass
        self._loop.run_forever()

    def get_loop(self) -> asyncio.AbstractEventLoop:
        return self._loop

    def run_sync(self, coro: Coroutine, timeout: float = 60.0) -> Any:
        """
        Synchronously run an async coroutine on the global background loop.
        """
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        try:
            return future.result(timeout=timeout)
        except Exception as e:
            if not future.done():
                future.cancel()
            raise e


# Singleton instance
bridge = GlobalBridge()


def get_global_loop():
    return bridge.get_loop()


def run_on_loop(coro: Coroutine, timeout: float = 60.0):
    return bridge.run_sync(coro, timeout=timeout)
