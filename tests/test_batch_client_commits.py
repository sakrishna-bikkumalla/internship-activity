import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.services.batch import client


@pytest.fixture
def mock_client():
    mc = MagicMock()
    # Mock _run_sync to just call the coroutine if possible, or use a real loop
    def run_sync(coro):
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()
    mc._run_sync.side_effect = run_sync
    return mc

def test_get_user_commits_matching(mock_client):
    ui = client.GitLabUsersAPI(mock_client)
    user_info = {"id": 1, "username": "jdoe", "email": "jdoe@example.com", "name": "John Doe"}
    
    # Mock projects
    with patch.object(ui, "get_user_projects", return_value=[{"id": 101, "name": "Proj1"}]):
        # Mock async_get_paginated for commits
        async def mock_async_get(*args, **kwargs):
            return [
                {
                    "id": "c1",
                    "author_email": "jdoe@example.com",
                    "author_name": "John Doe",
                    "created_at": "2024-01-01T00:00:00Z"
                },
                {
                    "id": "c2",
                    "author_email": "other@example.com",
                    "author_name": "Other",
                    "created_at": "2024-01-01T00:00:00Z"
                }
            ]
        mock_client._async_get_paginated = mock_async_get
        
        commits = ui.get_user_commits(user_info)
        assert len(commits) == 1
        assert commits[0]["id"] == "c1"
        assert commits[0]["project_name"] == "Proj1"

def test_get_user_commits_no_id():
    ui = client.GitLabUsersAPI(MagicMock())
    assert ui.get_user_commits({}) == []
    assert ui.get_user_commits(None) == []

def test_get_user_commits_no_projects(mock_client):
    ui = client.GitLabUsersAPI(mock_client)
    with patch.object(ui, "get_user_projects", return_value=[]):
        assert ui.get_user_commits({"id": 1}) == []
