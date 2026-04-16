from unittest.mock import MagicMock, patch

from gitlab_compliance_checker.infrastructure.gitlab import (
    api_helper,
    files_reader,
    parse_uvlock,
)

# ---------------- API HELPER TESTS ----------------


def test_extract_path_from_url():
    assert api_helper.extract_path_from_url("http://gl.com/group/proj.git") == "group/proj"
    assert api_helper.extract_path_from_url("http://gl.com/group/proj") == "group/proj"
    assert api_helper.extract_path_from_url("simple/path") == "simple/path"
    # test with None to trigger exception block
    assert api_helper.extract_path_from_url(None) == "None"


def test_get_project_branches():
    mock_gl = MagicMock()
    mock_gl._get_paginated.return_value = [{"name": "main"}]
    assert api_helper.get_project_branches(mock_gl, 123) == ["main"]

    mock_gl._get_paginated.side_effect = Exception("error")
    assert api_helper.get_project_branches(mock_gl, 123) == []


@patch("gitlab_compliance_checker.infrastructure.gitlab.api_helper.glabflow.Client")
@patch("gitlab_compliance_checker.infrastructure.gitlab.api_helper._run_sync")
def test_get_user_from_token(mock_run_sync, mock_client):
    import asyncio

    mock_gl = MagicMock()
    mock_gl.__aenter__.return_value = mock_gl

    async def mock_get(*args, **kwargs):
        return {"id": 1, "username": "test_user"}

    mock_gl.get = mock_get
    mock_client.return_value = mock_gl

    def run_coro(coro):
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)

    mock_run_sync.side_effect = run_coro

    result = api_helper.get_user_from_token("http://gl.local", "tok")
    assert isinstance(result, dict)
    assert result.get("username") == "test_user"


@patch("gitlab_compliance_checker.infrastructure.gitlab.api_helper.glabflow.Client")
@patch("gitlab_compliance_checker.infrastructure.gitlab.api_helper._run_sync")
def test_get_user_groups_by_token(mock_run_sync, mock_client):
    import asyncio

    mock_gl = MagicMock()
    mock_gl.__aenter__.return_value = mock_gl

    async def mock_paginate(*args, **kwargs):
        yield [{"id": 100, "name": "group_a"}]
        yield [{"id": 101, "name": "group_b"}]

    mock_gl.paginate = mock_paginate
    mock_client.return_value = mock_gl

    def run_coro(coro):
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(coro)

    mock_run_sync.side_effect = run_coro

    result = api_helper.get_user_groups_by_token("http://gl.local", "tok")
    assert isinstance(result, list)
    assert len(result) == 2
    assert result[0]["name"] == "group_a"
    assert result[1]["name"] == "group_b"


# ---------------- FILES READER TESTS ----------------


def test_read_file_content():
    mock_gl = MagicMock()
    # Content is "Hello" in base64
    mock_gl._get.return_value = {"content": "SGVsbG8="}
    assert files_reader.read_file_content(mock_gl, 123, "f.txt", "main") == "Hello"

    mock_gl._get.side_effect = Exception("404")
    assert files_reader.read_file_content(mock_gl, 123, "f.txt", "main") is None


def test_list_all_files():
    mock_gl = MagicMock()
    mock_gl._get_paginated.return_value = [{"path": "src/a.py", "type": "blob"}, {"path": "src", "type": "tree"}]
    assert files_reader.list_all_files(mock_gl, 123) == ["src/a.py"]

    mock_gl._get_paginated.side_effect = Exception("Fatal")
    assert files_reader.list_all_files(mock_gl, 123) == []


# ---------------- PARSE UVLOCK TESTS ----------------


def test_parse_uvlock_content():
    content = '[[package]]\nname = "pkg1"\nversion = "1.0"\n'
    res = parse_uvlock.parse_uvlock_content(content)
    assert res["total_dependencies"] == 1
    assert res["packages"][0]["name"] == "pkg1"

    assert "error" in parse_uvlock.parse_uvlock_content("invalid { toml")


def test_extract_dependencies_from_project():
    mock_gl = MagicMock()
    # "[[package]]\nname="x"" in base64 is W1twYWNrYWdlXV0KbmFtZT0ieCI=
    mock_gl._get.return_value = {"content": "W1twYWNrYWdlXV0KbmFtZT0ieCI="}
    res = parse_uvlock.extract_dependencies_from_project(mock_gl, 123)
    assert res["total_dependencies"] == 1

    mock_gl._get.side_effect = Exception("error")
    assert "error" in parse_uvlock.extract_dependencies_from_project(mock_gl, 123)
