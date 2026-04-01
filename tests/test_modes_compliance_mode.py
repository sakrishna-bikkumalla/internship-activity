import concurrent.futures
from unittest.mock import MagicMock, patch

import pytest
from gitlab import GitlabGetError

from modes import compliance_mode


@pytest.fixture
def mock_project():
    m = MagicMock()
    m.id = 123
    m.name_with_namespace = "Group / Project"
    m.default_branch = "main"
    return m


@pytest.fixture
def mock_gl_client():
    return MagicMock()


def test_extract_path_from_url():
    assert compliance_mode.extract_path_from_url("https://gitlab.com/gp/p1.git") == "gp/p1"
    assert compliance_mode.extract_path_from_url("gp/p2") == "gp/p2"
    assert compliance_mode.extract_path_from_url("12345") == "12345"


def test_get_project_branches(mock_project):
    b1 = MagicMock()
    b1.name = "main"
    b2 = MagicMock()
    b2.name = "develop"
    mock_project.branches.list.return_value = [b1, b2]

    branches = compliance_mode.get_project_branches(mock_project)
    assert branches == ["develop", "main"]


def test_get_project_branches_exception(mock_project):
    mock_project.branches.list.side_effect = Exception("error")
    assert compliance_mode.get_project_branches(mock_project) == []


def test_get_project_with_retries_success(mock_gl_client, mock_project):
    mock_gl_client.projects.get.return_value = mock_project
    res = compliance_mode.get_project_with_retries(mock_gl_client, "gp/p1")
    assert res == mock_project
    mock_gl_client.projects.get.assert_called_with("gp/p1")


def test_get_project_with_retries_fail(mock_gl_client):
    mock_gl_client.projects.get.side_effect = GitlabGetError()
    with pytest.raises(GitlabGetError):
        compliance_mode.get_project_with_retries(mock_gl_client, "bad/repo")


@patch("modes.compliance_mode.st")
@patch("modes.compliance_mode.get_project_with_retries")
@patch("modes.compliance_mode.run_project_compliance_checks")
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
    mock_project.branches.list.return_value = [MagicMock(name="main")]

    # First call to render
    compliance_mode.render_compliance_mode(mock_gl_client)

    mock_get.assert_called()


@patch("modes.compliance_mode.st")
@patch("modes.compliance_mode.get_project_with_retries")
@patch("modes.compliance_mode.run_project_compliance_checks")
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
