from unittest.mock import MagicMock, patch

import pytest
from gitlab import GitlabGetError

from gitlab_utils import api_helper, files_reader, network, parse_uvlock, retry_helper

# ---------------- API HELPER TESTS ----------------


def test_extract_path_from_url():
    assert api_helper.extract_path_from_url("http://gl.com/group/proj.git") == "group/proj"
    assert api_helper.extract_path_from_url("http://gl.com/group/proj") == "group/proj"
    assert api_helper.extract_path_from_url("simple/path") == "simple/path"
    # test with None to trigger exception block
    assert api_helper.extract_path_from_url(None) == "None"


def test_get_project_branches():
    project = MagicMock()
    mock_branch = MagicMock()
    mock_branch.name = "main"
    project.branches.list.return_value = [mock_branch]
    assert api_helper.get_project_branches(project) == ["main"]

    project.branches.list.side_effect = Exception("error")
    assert api_helper.get_project_branches(project) == []


@patch("aiohttp.ClientSession.get")
def test_get_user_from_token(mock_get):
    mock_response = MagicMock()
    
    # We need an async mock for json()
    from unittest.mock import AsyncMock
    mock_response.json = AsyncMock(return_value={"username": "user1"})
    
    # get() returns an async context manager
    mock_get.return_value.__aenter__.return_value = mock_response

    res = api_helper.get_user_from_token("http://gl.com", "token")
    assert res == {"username": "user1"}

    mock_get.side_effect = Exception("Fail")
    assert "Error validating token" in api_helper.get_user_from_token("http://gl.com", "token")


@patch("aiohttp.ClientSession.get")
def test_get_user_groups_by_token(mock_get):
    mock_response = MagicMock()
    from unittest.mock import AsyncMock
    mock_response.json = AsyncMock(return_value=[{"name": "g1"}])
    mock_get.return_value.__aenter__.return_value = mock_response

    # Path with /api/v4
    api_helper.get_user_groups_by_token("http://gl.com/api/v4", "token")
    assert mock_get.call_args.args[0] == "http://gl.com/api/v4/groups?membership=true"

    # Path without /api/v4
    api_helper.get_user_groups_by_token("http://gl.com", "token")
    assert mock_get.call_args.args[0] == "http://gl.com/api/v4/groups?membership=true"

    # Exception
    mock_get.side_effect = Exception("error")
    assert "Error fetching groups" in api_helper.get_user_groups_by_token("http://gl.com", "token")


# ---------------- FILES READER TESTS ----------------


def test_read_file_content():
    project = MagicMock()
    mock_file = MagicMock()
    mock_file.decode.return_value = b"Hello"
    project.files.get.return_value = mock_file
    assert files_reader.read_file_content(project, "f.txt", "main") == "Hello"

    project.files.get.side_effect = Exception("404")
    assert files_reader.read_file_content(project, "f.txt", "main") is None


def test_list_all_files():
    project = MagicMock()
    project.repository_tree.return_value = [{"path": "src/a.py", "type": "blob"}, {"path": "src", "type": "tree"}]
    assert files_reader.list_all_files(project) == ["src/a.py"]

    # Test TypeError fallback
    project.repository_tree.side_effect = [TypeError("old version"), [{"path": "b.py", "type": "blob"}]]
    assert files_reader.list_all_files(project) == ["b.py"]

    project.repository_tree.side_effect = Exception("Fatal")
    assert files_reader.list_all_files(project) == []


# ---------------- NETWORK TESTS ----------------


@patch("aiohttp.ClientSession.request")
def test_network_make_request(mock_req):
    mock_response = MagicMock()
    from unittest.mock import AsyncMock
    mock_response.json = AsyncMock(return_value={"id": 10})
    mock_req.return_value.__aenter__.return_value = mock_response
    assert network.make_request("GET", "http://test") == {"id": 10}
    mock_response.raise_for_status.assert_called_once()


@patch("gitlab_utils.network.make_request")
def test_network_get_user_from_token(mock_make):
    # network.make_request now returns the json directly, not a response object
    mock_make.return_value = {"id": 1}
    assert network.get_user_from_token("http://gl.com", "tok") == {"id": 1}
    assert network.validate_token("http://gl.com", "tok") is True

    mock_make.side_effect = Exception("Fail")
    assert network.validate_token("http://gl.com", "tok") is False


@patch("gitlab_utils.network.make_request")
def test_network_get_user_groups(mock_make):
    mock_make.return_value = []

    # Base url with /api/v4
    network.get_user_groups("http://gl.com/api/v4", "tok")
    # Base url without /api/v4
    network.get_user_groups("http://gl.com", "tok")
    assert mock_make.call_count == 2


# ---------------- PARSE UVLOCK TESTS ----------------


def test_parse_uvlock_content():
    content = '[[package]]\nname = "pkg1"\nversion = "1.0"\n'
    res = parse_uvlock.parse_uvlock_content(content)
    assert res["total_dependencies"] == 1
    assert res["packages"][0]["name"] == "pkg1"

    assert "error" in parse_uvlock.parse_uvlock_content("invalid { toml")


def test_extract_dependencies_from_project():
    project = MagicMock()
    mock_file = MagicMock()
    mock_file.decode.return_value = b'[[package]]\nname="x"'
    project.files.get.return_value = mock_file
    res = parse_uvlock.extract_dependencies_from_project(project)
    assert res["total_dependencies"] == 1

    project.files.get.side_effect = Exception("error")
    assert "error" in parse_uvlock.extract_dependencies_from_project(project)


# ---------------- RETRY HELPER TESTS ----------------


@patch("time.sleep")
def test_get_project_with_retries(mock_sleep):
    mock_gl = MagicMock()

    # Success on first try
    mock_gl.projects.get.return_value = "project"
    assert retry_helper.get_project_with_retries(mock_gl, "123") == "project"
    assert retry_helper.get_project_with_retries(mock_gl, 123) == "project"

    # 404 should raise immediately
    mock_response = MagicMock()
    mock_response.status_code = 404
    err_404 = GitlabGetError()
    err_404.response = mock_response
    mock_gl.projects.get.side_effect = err_404
    with pytest.raises(GitlabGetError):
        retry_helper.get_project_with_retries(mock_gl, "path")

    # Other GitlabGetError retry
    mock_response_500 = MagicMock()
    mock_response_500.status_code = 500
    err_500 = GitlabGetError()
    err_500.response = mock_response_500
    mock_gl.projects.get.side_effect = [err_500, "project"]
    assert retry_helper.get_project_with_retries(mock_gl, "path", retries=2) == "project"

    # ConnectionResetError retry
    mock_gl.projects.get.side_effect = [ConnectionResetError(), "project"]
    assert retry_helper.get_project_with_retries(mock_gl, "path", retries=2) == "project"

    # Exhaust retries with GitlabGetError
    mock_gl.projects.get.side_effect = err_500
    with pytest.raises(GitlabGetError):
        retry_helper.get_project_with_retries(mock_gl, "path", retries=2)

    # Exhaust retries with ConnectionResetError
    mock_gl.projects.get.side_effect = ConnectionResetError("reset")
    with pytest.raises(ConnectionResetError):
        retry_helper.get_project_with_retries(mock_gl, "path", retries=2)
