from unittest.mock import MagicMock, patch

import pytest

# GitlabGetError is replaced by generic Exception or glabflow exceptions in production.
# In tests, we will use Exception or a mock if needed.
from gitlab_compliance_checker.ui import compliance as compliance_mode


@pytest.fixture
def mock_project():
    # project is now a dict
    return {
        "id": 123,
        "name_with_namespace": "Group / Project",
        "path_with_namespace": "gp/p1",
        "default_branch": "main",
    }


@pytest.fixture
def mock_gl_client():
    m = MagicMock()
    # Mocking the new wrapper methods
    m._get.return_value = {}
    m._get_paginated.return_value = []
    return m


def test_extract_path_from_url():
    assert compliance_mode.extract_path_from_url("https://gitlab.com/gp/p1.git") == "gp/p1"
    assert compliance_mode.extract_path_from_url("gp/p2") == "gp/p2"
    assert compliance_mode.extract_path_from_url("12345") == "12345"


def test_get_project_branches(mock_gl_client):
    # This now calls api_get_branches(gl_client, project_id)
    # Which calls gl_client._get_paginated(f"/projects/{pid}/repository/branches", ...)
    mock_gl_client._get_paginated.return_value = [{"name": "main"}, {"name": "develop"}]

    branches = compliance_mode.get_project_branches(mock_gl_client, 123)
    assert branches == ["develop", "main"]


def test_get_project_branches_exception(mock_gl_client):
    mock_gl_client._get_paginated.side_effect = Exception("error")
    assert compliance_mode.get_project_branches(mock_gl_client, 123) == []


def test_get_project_with_retries_success(mock_gl_client, mock_project):
    mock_gl_client._get.return_value = mock_project
    res = compliance_mode.get_project_with_retries(mock_gl_client, "gp/p1")
    assert res == mock_project
    mock_gl_client._get.assert_called_with("/projects/gp%2Fp1")


def test_get_project_with_retries_fail(mock_gl_client):
    mock_gl_client._get.side_effect = Exception("404 Not Found")
    with pytest.raises(Exception, match="404 Not Found"):
        compliance_mode.get_project_with_retries(mock_gl_client, "bad/repo")


@patch("gitlab_compliance_checker.ui.compliance.st")
@patch("gitlab_compliance_checker.ui.compliance.get_project_with_retries")
@patch("gitlab_compliance_checker.ui.compliance.run_project_compliance_checks")
def test_render_compliance_mode_single_project(mock_run, mock_get, mock_st, mock_gl_client, mock_project):
    # Mock tabs
    tab1, tab2 = MagicMock(), MagicMock()
    mock_st.tabs.return_value = [tab1, tab2]

    # Mock columns
    col1, col2 = MagicMock(), MagicMock()
    mock_st.columns.return_value = [col1, col2]

    # Mock inputs for Single Project
    mock_st.text_input.return_value = "gp/p1"
    mock_st.button.side_effect = lambda label, key=None: label == "Fetch Project & Branches"

    mock_get.return_value = mock_project

    # Mocking api_get_branches call
    with patch("gitlab_compliance_checker.ui.compliance.api_get_branches") as mock_api:
        mock_api.return_value = ["main"]
        # First call to render
        compliance_mode.render_compliance_mode(mock_gl_client)

    mock_get.assert_called()


@patch("gitlab_compliance_checker.ui.compliance.st")
@patch("gitlab_compliance_checker.ui.compliance.get_project_with_retries")
@patch("gitlab_compliance_checker.ui.compliance.run_project_compliance_checks")
def test_render_batch_project_compliance_internal(mock_run, mock_get, mock_st, mock_gl_client, mock_project):
    mock_st.text_area.return_value = "gp/p1\ngp/p2"
    mock_st.button.return_value = True

    mock_get.return_value = mock_project
    mock_run.return_value = {
        "dx_score": 90,
        "tools": {"project_type": "Python", "security": {}, "testing": {}, "automation": {}},
        "license": {"valid": True},
    }

    compliance_mode.render_batch_project_compliance_internal(mock_gl_client)

    assert mock_get.call_count == 2
    mock_st.dataframe.assert_called()
