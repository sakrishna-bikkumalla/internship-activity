from unittest.mock import MagicMock

from gitlab_utils.groups import get_user_groups
from gitlab_utils.issues import get_user_issues
from gitlab_utils.projects import get_user_projects, search_projects
from gitlab_utils.users import get_user_by_username

# ---------------- USERS TESTS ----------------

def test_get_user_by_username():
    mock_client = MagicMock()
    # Found
    mock_client._get.return_value = [{"id": 1, "username": "testuser"}]
    res = get_user_by_username(mock_client, "testuser")
    assert res["id"] == 1

    # Not found
    mock_client._get.return_value = []
    assert get_user_by_username(mock_client, "none") is None

    # Invalid response
    mock_client._get.return_value = None
    assert get_user_by_username(mock_client, "none") is None

# ---------------- GROUPS TESTS ----------------

def test_get_user_groups():
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [
        {"id": 101, "name": "Group 1", "full_path": "g1", "visibility": "public"},
        {"id": 101, "name": "Group 1 Duplicate", "full_path": "g1", "visibility": "public"},
        {"id": 102, "name": "Group 2", "full_path": "g2", "visibility": "private"},
    ]

    res = get_user_groups(mock_client, 1)
    assert len(res) == 2 # Deduplicated
    assert res[0]["name"] == "Group 1"
    assert res[1]["visibility"] == "private"

def test_get_user_groups_exception():
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = Exception("error")
    assert get_user_groups(mock_client, 1) == []

# ---------------- ISSUES TESTS ----------------

def test_get_user_issues():
    mock_client = MagicMock()
    mock_client._get_paginated.return_value = [
        {"id": 1, "title": "Issue 1", "project_id": 10, "state": "opened"},
        {"id": 2, "title": "Issue 2", "project_id": 20, "state": "closed"},
    ]

    # No filters
    issues, stats = get_user_issues(mock_client, 1)
    assert stats["total"] == 2
    assert stats["opened"] == 1
    assert stats["closed"] == 1

    # With project filter
    issues, stats = get_user_issues(mock_client, 1, project_ids=[10])
    assert stats["total"] == 1
    assert issues[0]["project_id"] == 10

    # With date filters (passed to API)
    get_user_issues(mock_client, 1, since="2024-01-01", until="2024-01-31")
    kwargs = mock_client._get_paginated.call_args.kwargs
    assert kwargs["params"]["created_after"] == "2024-01-01"
    assert kwargs["params"]["created_before"] == "2024-01-31"

def test_get_user_issues_exception():
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = Exception("error")
    issues, stats = get_user_issues(mock_client, 1)
    assert issues == []
    assert stats["total"] == 0

# ---------------- PROJECTS TESTS ----------------

def test_get_user_projects_success():
    mock_client = MagicMock()

    # projects_data
    mock_client._get_paginated.side_effect = [
        [{"id": 1, "name": "Project 1", "namespace": {"path": "user1", "kind": "user"}}], # projects
        [{"project_id": 2}] # events
    ]

    # extra details for project 2
    mock_client._get.return_value = {"id": 2, "name": "Project 2", "namespace": {"path": "group1", "kind": "group"}}

    res = get_user_projects(mock_client, 1, "user1")
    assert len(res["all"]) == 2
    assert len(res["personal"]) == 1 # Project 1
    assert len(res["contributed"]) == 1 # Project 2
    assert res["personal"][0]["id"] == 1
    assert res["contributed"][0]["id"] == 2

def test_get_user_projects_exception():
    mock_client = MagicMock()
    mock_client._get_paginated.side_effect = Exception("error")
    res = get_user_projects(mock_client, 1, "user")
    assert res == {"personal": [], "contributed": [], "all": []}

def test_search_projects():
    mock_client = MagicMock()
    mock_client._get.return_value = [{"id": 1}]
    res = search_projects(mock_client, "query")
    assert res == [{"id": 1}]
    args = mock_client._get.call_args
    assert args.kwargs["params"]["search"] == "query"
