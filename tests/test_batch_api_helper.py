from unittest.mock import MagicMock, patch

from gitlab_compliance_checker.services.batch import api_helper


def test_extract_path_from_url():
    assert api_helper.extract_path_from_url("http://gl.com/group/proj.git") == "group/proj"
    assert api_helper.extract_path_from_url("http://gl.com/group/proj") == "group/proj"
    # Trigger exception
    with patch("urllib.parse.urlparse", side_effect=Exception):
        assert api_helper.extract_path_from_url("raw_path") == "raw_path"


def test_get_project_branches():
    client = MagicMock()
    # In api_helper.py: get_project_branches(gl_client, project_id)
    # calls gl_client._get_paginated(f"/projects/{pid}/repository/branches", all=True)
    client._get_paginated.return_value = [{"name": "main"}, {"name": "dev"}]
    assert api_helper.get_project_branches(client, 123) == ["dev", "main"]

    client._get_paginated.side_effect = Exception("error")
    assert api_helper.get_project_branches(client, 123) == []


def test_list_all_files():
    client = MagicMock()
    client._get_paginated.return_value = [{"path": "f1.py", "type": "blob"}, {"path": "d1", "type": "tree"}]
    assert api_helper.list_all_files(client, 123) == ["f1.py"]

    client._get_paginated.side_effect = Exception("error")
    assert api_helper.list_all_files(client, 123) == []


def test_classify_repository_files():
    files = [
        "requirements.txt",
        "README.md",
        "Dockerfile",
        "src/main.py",
        "tests/test.py",
        "style.js",
        ".vscode/settings.json",
    ]
    res = api_helper.classify_repository_files(files)
    assert "requirements.txt" in res["common_requirements"]
    assert "README.md" in res["project_files"]
    assert "Dockerfile" in res["tech_files"]
    assert "src/main.py" in res["python_files"]
    assert "style.js" in res["js_files"]

    # Empty case
    assert api_helper.classify_repository_files(None) == {
        "common_requirements": [],
        "project_files": [],
        "tech_files": [],
        "python_files": [],
        "js_files": [],
        "java_files": [],
        "c#_files": [],
    }


def test_check_vscode_settings():
    client = MagicMock()
    client._get.return_value = [{"name": "settings.json"}]
    assert api_helper.check_vscode_settings(client, 123) is True

    client._get.side_effect = Exception("error")
    assert api_helper.check_vscode_settings(client, 123) is False


def test_check_vscode_file_exists():
    client = MagicMock()
    client._get.return_value = [{"name": "launch.json"}]
    assert api_helper.check_vscode_file_exists(client, 123, "launch.json") is True

    client._get.side_effect = Exception("error")
    assert api_helper.check_vscode_file_exists(client, 123, "launch.json") is False


def test_check_extensions_json_for_ruff():
    client = MagicMock()

    def mock_read(c, p, f, b):
        if f == ".vscode/extensions.json":
            return '{"recommendations": ["charliermarsh.ruff"]}'
        return None

    assert api_helper.check_extensions_json_for_ruff(client, 123, read_file_fn=mock_read) is True
    assert api_helper.check_extensions_json_for_ruff(client, 123, read_file_fn=lambda c, p, f, b: None) is False
    assert api_helper.check_extensions_json_for_ruff(client, 123, read_file_fn=lambda c, p, f, b: "{invalid}") is False


def test_list_markdown_files_in_folder():
    client = MagicMock()
    client._get.return_value = [{"name": "doc1.md"}, {"name": "doc2.txt"}]
    assert api_helper.list_markdown_files_in_folder(client, 123, "docs") == ["doc1.md"]

    client._get.side_effect = Exception("error")
    assert api_helper.list_markdown_files_in_folder(client, 123, "docs") == []


def test_check_templates_presence():
    client = MagicMock()

    def mock_tree(url, params=None):
        path = (params or {}).get("path", "")
        if path == ".gitlab/issue_templates":
            return [{"name": "bug.md"}]
        if path == ".gitlab/merge_request_templates":
            return [{"name": "mr.md"}]
        return []

    client._get.side_effect = mock_tree
    res = api_helper.check_templates_presence(client, 123)
    assert res["issue_templates_folder"] is True
    assert "bug.md" in res["issue_template_files"]
    assert res["merge_request_templates_folder"] is True
    assert "mr.md" in res["merge_request_template_files"]

    client._get.side_effect = Exception("fail")
    res = api_helper.check_templates_presence(client, 123)
    assert res["issue_templates_folder"] is False


def test_check_license_content():
    client = MagicMock()

    # Valid AGPLv3
    agpl_content = "GNU Affero General Public License version 3 19 November 2007"
    assert api_helper.check_license_content(client, 123, read_file_fn=lambda c, p, f, b: agpl_content) == "valid"

    # GPLv3
    gpl_content = "GNU General Public License version 3 29 June 2007"
    assert api_helper.check_license_content(client, 123, read_file_fn=lambda c, p, f, b: gpl_content) == "gnu_other"

    # MIT
    assert api_helper.check_license_content(client, 123, read_file_fn=lambda c, p, f, b: "MIT License") == "invalid"

    # Not found
    assert api_helper.check_license_content(client, 123, read_file_fn=lambda c, p, f, b: None) == "not_found"


def test_check_project_compliance():
    client = MagicMock()
    client._get.side_effect = [
        {"default_branch": "main", "description": "Test", "tag_list": ["tag1"]},  # Info call
        [{"name": "README.md"}, {"name": "LICENSE"}, {"name": ".gitignore"}],  # Tree call
    ]

    def mock_read(c, p, f, b):
        if f == "README.md":
            return "Installation Usage Setup"
        if f == "LICENSE":
            return "GNU Affero General Public License version 3 19 November 2007"
        return None

    res = api_helper.check_project_compliance(client, 123, read_file_fn=mock_read)
    assert res["README.md"] is True
    assert res["LICENSE"] is True
    assert res["license_status"] == "valid"


def test_check_project_compliance_extended():
    client = MagicMock()
    # Case: Empty tree
    client._get.side_effect = [
        {"default_branch": "main", "description": ""},
        [],  # Tree
    ]
    res = api_helper.check_project_compliance(client, 123, read_file_fn=lambda c, p, f, b: None)
    assert res["README.md"] is False
    assert res["license_status"] == "not_found"

    # CASE: Exception
    client._get.side_effect = Exception("Crash")
    res = api_helper.check_project_compliance(client, 123)
    assert "error" in res


def test_classify_repository_files_edge_cases():
    files = ["setup.py", "pyproject.toml", "src/main.py"]
    res = api_helper.classify_repository_files(files)
    assert "setup.py" in res["common_requirements"]
    assert "pyproject.toml" in res["common_requirements"]
    assert "src/main.py" in res["project_files"]
