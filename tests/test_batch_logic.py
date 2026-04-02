from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.infrastructure.gitlab import batch, projects


@pytest.fixture
def mock_client():
    client = MagicMock()
    # Mock _get_paginated to return a list
    client._get_paginated.return_value = []
    return client


def test_project_classification_personal(mock_client):
    """Test that projects are correctly classified as personal."""
    username = "testuser"
    user_id = 123

    # Mock project data
    mock_projects = [
        {"id": 1, "name": "Personal Project", "namespace": {"path": "testuser", "kind": "user"}},
        {
            "id": 2,
            "name": "Contributed Project",
            "namespace": {"path": "otheruser", "kind": "user"},
        },
        {"id": 3, "name": "Group Project", "namespace": {"path": "somegroup", "kind": "group"}},
    ]

    mock_client._get_paginated.return_value = mock_projects

    res = projects.get_user_projects(mock_client, user_id, username)

    assert len(res["personal"]) == 1
    assert res["personal"][0]["id"] == 1
    assert len(res["contributed"]) == 2
    assert res["contributed"][0]["id"] == 2
    assert res["contributed"][1]["id"] == 3


@patch("gitlab_compliance_checker.infrastructure.gitlab.users.get_user_by_username")
@patch("gitlab_compliance_checker.infrastructure.gitlab.projects.get_user_projects")
@patch("gitlab_compliance_checker.infrastructure.gitlab.commits.get_user_commits")
@patch("gitlab_compliance_checker.infrastructure.gitlab.groups.get_user_groups")
@patch("gitlab_compliance_checker.infrastructure.gitlab.merge_requests.get_user_mrs")
@patch("gitlab_compliance_checker.infrastructure.gitlab.issues.get_user_issues")
def test_process_single_user_success(
    mock_issues, mock_mrs, mock_groups, mock_commits, mock_projects, mock_users, mock_client
):
    """Test successful user processing logic."""
    username = "testuser"
    user_id = 123

    mock_users.return_value = {"id": user_id, "username": username, "name": "Test User"}
    mock_projects.return_value = {
        "personal": [{"id": 1}],
        "contributed": [{"id": 2}],
        "all": [{"id": 1}, {"id": 2}],
    }
    mock_commits.return_value = ([], {1: 10, 2: 5}, {"total": 15})
    mock_groups.return_value = []
    mock_mrs.return_value = ([], {"total": 0})
    mock_issues.return_value = ([], {"total": 0})

    result = batch.process_single_user(mock_client, username)

    assert result["status"] == "Success"
    assert result["username"] == username
    assert "projects" in result["data"]
    assert len(result["data"]["projects"]["personal"]) == 1
    assert len(result["data"]["projects"]["contributed"]) == 1
