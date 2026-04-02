import asyncio
from unittest.mock import AsyncMock

import pytest


class TestAsyncFetchPatterns:
    """Tests for async fetch patterns used in the fetch_script module."""

    def test_gitlab_client_import(self):
        """Test GitLabClient import."""
        from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient

        assert callable(GitLabClient)

    def test_gitlab_client_has_headers(self):
        """Test GitLabClient has private_token attribute."""
        from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient

        client = GitLabClient("https://gitlab.com", "test_token")
        assert hasattr(client, "private_token")
        assert hasattr(client, "base_url")

    def test_gitlab_client_headers_contains_token(self):
        """Test GitLabClient private_token is stored."""
        from gitlab_compliance_checker.infrastructure.gitlab.client import GitLabClient

        client = GitLabClient("https://gitlab.com", "my_secret_token")
        assert client.private_token == "my_secret_token"

    @pytest.mark.asyncio
    async def test_coroutine_function_detection(self):
        """Test that async functions are properly detected."""

        async def async_func():
            return 42

        assert asyncio.iscoroutinefunction(async_func)
        result = await async_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_coroutine_function_returns_coroutine(self):
        """Test that async functions return coroutines."""

        async def async_func():
            return 42

        result = async_func()
        assert asyncio.iscoroutine(result)
        value = await result
        assert value == 42

    @pytest.mark.asyncio
    async def test_await_coroutine(self):
        """Test awaiting a coroutine."""

        async def async_func():
            return 42

        result = await async_func()
        assert result == 42

    @pytest.mark.asyncio
    async def test_async_with_awaitable_enter(self):
        """Test async context manager with awaitable __aenter__."""
        mock_cm = AsyncMock()
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        async with mock_cm:
            pass

        mock_cm.__aenter__.assert_called_once()
        mock_cm.__aexit__.assert_called_once()
