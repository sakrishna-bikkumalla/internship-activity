import asyncio
from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.services.batch import client


@pytest.fixture
def mock_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()

def test_decode():
    assert client._decode({"a": 1}) == {"a": 1}
    assert client._decode(b'{"a": 1}') == {"a": 1}
    assert client._decode(b'invalid') == []
    assert client._decode(None) == []

@patch("gitlab_compliance_checker.services.batch.client.get_global_loop")
@patch("glabflow.Client")
def test_gitlab_client_init(mock_gl_cls, mock_get_loop, mock_loop):
    mock_get_loop.return_value = mock_loop
    mock_gl = MagicMock()
    mock_gl.__aenter__.return_value = mock_gl
    mock_gl_cls.return_value = mock_gl
    
    gc = client.GitLabClient("http://gitlab.com", "token")
    assert gc.base_url == "http://gitlab.com"
    assert gc.users is not None

@patch("gitlab_compliance_checker.services.batch.client.get_global_loop")
def test_gitlab_users_api_normalize(mock_get_loop, mock_loop):
    mock_get_loop.return_value = mock_loop
    ui = client.GitLabUsersAPI(MagicMock())
    user = {"id": 1, "username": "u", "name": "N", "web_url": "W", "avatar_url": "A", "public_email": "E"}
    norm = ui._normalize_user(user)
    assert norm["id"] == 1
    assert norm["email"] == "E"
    assert ui._normalize_user(None) is None

@patch("gitlab_compliance_checker.services.batch.client.run_on_loop")
def test_get_user_projects(mock_run_sync):
    mc = MagicMock()
    ui = client.GitLabUsersAPI(mc)
    
    # Mock three paginated calls
    mc._get_paginated.side_effect = [
        [{"id": 1, "name": "P1"}], # owned
        [{"id": 2, "name": "P2"}], # membership
        [{"id": 1, "name": "P1"}]  # contributed (duplicate)
    ]
    
    projects = ui.get_user_projects(123)
    assert len(projects) == 2
    ids = {p["id"] for p in projects}
    assert ids == {1, 2}

@patch("gitlab_compliance_checker.services.batch.client.run_on_loop")
def test_get_user_counts_errors(mock_run_sync):
    mc = MagicMock()
    ui = client.GitLabUsersAPI(mc)
    mc._get_paginated.side_effect = Exception("API Error")
    
    # These functions swallow exceptions and return error strings or 0
    assert "Error" in ui.get_user_project_count(123)
    assert "Error" in ui.get_user_group_count(123)
    assert "Error" in ui.get_user_issue_count(123)
    assert "Error" in ui.get_user_mr_count(123)

def test_get_by_username_fail():
    mc = MagicMock()
    mc._get.return_value = []
    ui = client.GitLabUsersAPI(mc)
    with pytest.raises(ValueError):
        ui.get_by_username("missing")
