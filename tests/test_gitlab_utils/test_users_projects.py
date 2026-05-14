from unittest.mock import AsyncMock, MagicMock

import pytest

from internship_activity_tracker.infrastructure.gitlab.projects import get_user_projects, get_user_projects_async
from internship_activity_tracker.infrastructure.gitlab.users import get_user_by_username, get_user_by_username_async


@pytest.mark.asyncio
async def test_get_user_by_username_async_success():
    mock_client = MagicMock()
    mock_client._async_get = AsyncMock()
    mock_client._async_get.side_effect = [
        [{"id": 123, "username": "testuser"}],  # /users?username=testuser
        {"id": 123, "username": "testuser", "name": "Test User"},  # /users/123
    ]

    result = await get_user_by_username_async(mock_client, "testuser")
    assert result["id"] == 123
    assert result["name"] == "Test User"


@pytest.mark.asyncio
async def test_get_user_by_username_async_fallback():
    mock_client = MagicMock()
    mock_client._async_get = AsyncMock()
    mock_client._async_get.side_effect = [
        [],  # /users?username=testuser (Empty)
        [{"id": 456, "username": "testuser"}],  # /users?search=testuser
        {"id": 456, "username": "testuser", "name": "Full Data"},  # /users/456
    ]

    result = await get_user_by_username_async(mock_client, "testuser")
    assert result["id"] == 456
    assert result["name"] == "Full Data"


def test_get_user_by_username_sync():
    mock_client = MagicMock()
    mock_client._get.side_effect = [
        [{"id": 789, "username": "SyncUser"}],
        {"id": 789, "username": "SyncUser", "extra": "data"},
    ]

    result = get_user_by_username(mock_client, "syncuser")
    assert result["id"] == 789
    assert result["extra"] == "data"


@pytest.mark.asyncio
async def test_get_user_projects_async():
    mock_client = MagicMock()
    mock_client._async_get_paginated = AsyncMock()
    mock_client._async_get = AsyncMock()

    mock_client._async_get_paginated.side_effect = [
        [{"id": 1, "name": "P1", "namespace": {"path": "u1", "kind": "user"}}],  # projects
        [{"project_id": 2}],  # events
    ]
    mock_client._async_get.return_value = {"id": 2, "name": "P2", "namespace": {"path": "g1", "kind": "group"}}

    result = await get_user_projects_async(mock_client, 101, "u1")
    assert len(result["personal"]) == 1
    assert len(result["contributed"]) == 1
    assert result["all"][0]["id"] == 1
    assert result["all"][1]["id"] == 2


def test_get_user_projects_sync():
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = [[{"id": 10, "namespace": {"path": "me", "kind": "user"}}], []]
    result = get_user_projects(mock_client, 1, "me")
    assert len(result["personal"]) == 1
    assert result["personal"][0]["id"] == 10
