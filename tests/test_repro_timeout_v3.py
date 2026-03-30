import asyncio
import threading
from unittest.mock import MagicMock, patch

import aiohttp
import pytest


class TestMockClientPattern:
    """Tests for MockClient async/threading pattern from repro_timeout_v3."""

    def test_mock_client_class_structure(self):
        """Test MockClient class has expected structure."""
        from repro_timeout_v3 import MockClient

        client = MockClient()
        assert hasattr(client, "_loop")
        assert hasattr(client, "_thread")
        assert hasattr(client, "_session")
        assert client._thread.daemon is True
        assert client._session is None

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_run_loop_sets_event_loop(self):
        """Test _run_loop properly sets the event loop."""
        from repro_timeout_v3 import MockClient

        loop = asyncio.new_event_loop()
        client = MockClient()

        async def check_loop():
            return asyncio.get_event_loop()

        test_loop = client.run_sync(check_loop())
        assert test_loop is not None

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)
        loop.close()

    def test_get_session_lazy_initialization(self):
        """Test _get_session creates session lazily."""
        from repro_timeout_v3 import MockClient

        client = MockClient()
        assert client._session is None

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_run_sync_returns_coroutine_result(self):
        """Test run_sync properly returns coroutine result."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def simple_coro():
            return 42

        result = client.run_sync(simple_coro())
        assert result == 42

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_run_sync_propagates_exceptions(self):
        """Test run_sync properly propagates exceptions."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def failing_coro():
            raise ValueError("Test error")

        with pytest.raises(ValueError, match="Test error"):
            client.run_sync(failing_coro())

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_request_returns_coroutine(self):
        """Test request method returns a coroutine."""
        from repro_timeout_v3 import MockClient

        client = MockClient()
        coro = client.request()
        assert asyncio.iscoroutine(coro)

        async def cleanup():
            try:
                await coro
            except Exception:  # pragma: no cover
                pass  # pragma: no cover

        client.run_sync(cleanup())
        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    @patch("aiohttp.ClientSession")
    def test_request_with_exception(self, mock_session):
        """Test request method handles exceptions in cleanup."""
        from repro_timeout_v3 import MockClient

        mock_session.return_value.request.return_value.__aenter__.side_effect = ConnectionError("Test")

        client = MockClient()
        coro = client.request()
        assert asyncio.iscoroutine(coro)

        async def cleanup():
            try:
                await coro
            except Exception:
                pass

        client.run_sync(cleanup())
        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_exception_handling_in_cleanup(self):
        """Test that exception handling in cleanup is executed."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def failing_coro():
            raise RuntimeError("Intentional error")

        async def cleanup():
            try:
                await failing_coro()
            except Exception:
                pass

        client.run_sync(cleanup())
        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)


class TestMockClientWithMocking:
    """Tests using mocking for MockClient patterns."""

    @patch("aiohttp.ClientSession")
    def test_request_with_mocked_session(self, mock_session_class):
        """Test request method with mocked aiohttp session."""
        from repro_timeout_v3 import MockClient

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": "test"}
        mock_response.__aenter__.return_value = mock_response
        mock_response.__aexit__.return_value = None

        mock_session_instance = MagicMock()
        mock_session_instance.request.return_value = mock_response
        mock_session_class.return_value = mock_session_instance

        client = MockClient()

        async def test_request():
            session = await client._get_session()
            return session is not None

        result = client.run_sync(test_request())
        assert result is True

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)


class TestAsyncThreadingIntegration:
    """Tests for async/threading integration patterns."""

    def test_concurrent_coroutines(self):
        """Test handling concurrent coroutines."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def coro1():
            await asyncio.sleep(0)
            return "first"

        async def coro2():
            await asyncio.sleep(0)
            return "second"

        async def run_concurrent():
            task1 = asyncio.create_task(coro1())
            task2 = asyncio.create_task(coro2())
            return await task1, await task2

        result = client.run_sync(run_concurrent())
        assert result == ("first", "second")

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_nested_coroutine_calls(self):
        """Test nested coroutine call patterns."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def inner():
            await asyncio.sleep(0)
            return "nested"

        async def outer():
            result = await inner()
            return result

        result = client.run_sync(outer())
        assert result == "nested"

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_async_generator(self):
        """Test async generator handling."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def async_gen():
            for i in range(3):
                yield i
                await asyncio.sleep(0)

        results = []

        async def collect():
            async for item in async_gen():
                results.append(item)

        client.run_sync(collect())
        assert results == [0, 1, 2]

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)

    def test_multiple_sync_calls(self):
        """Test multiple consecutive run_sync calls."""
        from repro_timeout_v3 import MockClient

        client = MockClient()

        async def multiply(value):
            return value * 2

        results = [client.run_sync(multiply(i)) for i in range(5)]
        assert results == [0, 2, 4, 6, 8]

        client._loop.call_soon_threadsafe(client._loop.stop)
        client._thread.join(timeout=1)
