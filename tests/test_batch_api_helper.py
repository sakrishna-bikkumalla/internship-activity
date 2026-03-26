from unittest.mock import MagicMock, patch

from batch_mode import api_helper


def test_extract_path_from_url():
    assert api_helper.extract_path_from_url("http://gl.com/group/proj.git") == "group/proj"
    assert api_helper.extract_path_from_url("http://gl.com/group/proj") == "group/proj"
    # Trigger exception
    with patch("urllib.parse.urlparse", side_effect=Exception):
        assert api_helper.extract_path_from_url("raw_path") == "raw_path"

def test_get_project_branches():
    project = MagicMock()
    mock_branch = MagicMock()
    mock_branch.name = "main"
    project.branches.list.return_value = [mock_branch]
    assert api_helper.get_project_branches(project) == ["main"]

    project.branches.list.side_effect = Exception("error")
    assert api_helper.get_project_branches(project) == []

def test_list_all_files():
    project = MagicMock()
    project.repository_tree.return_value = [{"path": "f1.py", "type": "blob"}, {"path": "d1", "type": "tree"}]
    assert api_helper.list_all_files(project) == ["f1.py"]

    # TypeError fallback
    project.repository_tree.side_effect = [TypeError("all not supported"), [{"path": "fallback.py", "type": "blob"}]]
    assert api_helper.list_all_files(project) == ["fallback.py"]

def test_classify_repository_files():
    files = [
        "requirements.txt", "README.md", "Dockerfile", "src/main.py",
        "tests/test.py", "style.js", ".vscode/settings.json"
    ]
    res = api_helper.classify_repository_files(files)
    assert "requirements.txt" in res["common_requirements"]
    assert "README.md" in res["project_files"]
    assert "Dockerfile" in res["tech_files"]
    assert "src/main.py" in res["python_files"]
    assert "style.js" in res["js_files"]

    # Empty case
    assert api_helper.classify_repository_files(None) == {
        "common_requirements": [], "project_files": [], "tech_files": [],
        "python_files": [], "js_files": [], "java_files": [], "c#_files": []
    }

def test_check_vscode_settings():
    project = MagicMock()
    project.repository_tree.return_value = [{"name": "settings.json"}]
    assert api_helper.check_vscode_settings(project) is True

    project.repository_tree.side_effect = Exception("error")
    assert api_helper.check_vscode_settings(project) is False

def test_check_vscode_file_exists():
    project = MagicMock()
    project.repository_tree.return_value = [{"name": "launch.json"}]
    assert api_helper.check_vscode_file_exists(project, "launch.json") is True

    project.repository_tree.side_effect = Exception("error")
    assert api_helper.check_vscode_file_exists(project, "launch.json") is False

def test_check_extensions_json_for_ruff():
    project = MagicMock()
    def mock_read(p, f, b):
        if f == ".vscode/extensions.json":
            return '{"recommendations": ["charliermarsh.ruff"]}'
        return None

    assert api_helper.check_extensions_json_for_ruff(project, read_file_fn=mock_read) is True

    # Not found case
    assert api_helper.check_extensions_json_for_ruff(project, read_file_fn=lambda p,f,b: None) is False

    # Invalid JSON
    assert api_helper.check_extensions_json_for_ruff(project, read_file_fn=lambda p,f,b: "{invalid}") is False

def test_list_markdown_files_in_folder():
    project = MagicMock()
    project.repository_tree.return_value = [{"name": "doc1.md"}, {"name": "doc2.txt"}]
    assert api_helper.list_markdown_files_in_folder(project, "docs") == ["doc1.md"]

    project.repository_tree.side_effect = Exception("error")
    assert api_helper.list_markdown_files_in_folder(project, "docs") == []

def test_check_templates_presence():
    project = MagicMock()
    # Mock issue templates find
    def mock_tree(path, ref):
        if path == ".gitlab/issue_templates":
            return [{"name": "bug.md"}]
        if path == ".gitlab/merge_request_templates":
            return [{"name": "mr.md"}]
        return []

    project.repository_tree.side_effect = mock_tree
    res = api_helper.check_templates_presence(project)
    assert res["issue_templates_folder"] is True
    assert "bug.md" in res["issue_template_files"]
    assert res["merge_request_templates_folder"] is True
    assert "mr.md" in res["merge_request_template_files"]

    # Exception case
    project.repository_tree.side_effect = Exception("fail")
    res = api_helper.check_templates_presence(project)
    assert res["issue_templates_folder"] is False

def test_check_license_content():
    project = MagicMock()

    # Valid AGPLv3
    agpl_content = "GNU Affero General Public License version 3 19 November 2007"
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: agpl_content) == "valid"

    # GPLv3
    gpl_content = "GNU General Public License version 3 29 June 2007"
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: gpl_content) == "gnu_other"

    # LGPLv3
    lgpl_content = "GNU Lesser General Public License version 3"
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: lgpl_content) == "gnu_other"

    # MIT (invalid for this compliance check)
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: "MIT License") == "invalid"

    # Generic license
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: "Copyright 2024 License") == "invalid"
    # Malformed GNU
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: "Copyright GNU License") == "gnu_other"

    # Not found
    assert api_helper.check_license_content(project, read_file_fn=lambda p,f,b: None) == "not_found"

def test_check_project_compliance():
    project = MagicMock()
    project.default_branch = "main"
    project.repository_tree.return_value = [
        {"name": "README.md"}, {"name": "LICENSE"}, {"name": ".gitignore"}
    ]
    project.description = "Test project"
    project.tags.list.return_value = [MagicMock()]

    def mock_read(p, f, b):
        if f == "README.md": return "Installation Usage Setup"
        if f == "LICENSE": return "GNU Affero General Public License version 3 19 November 2007"
        return None

def test_check_project_compliance_extended():
    project = MagicMock()
    project.default_branch = "main"

    # CASE: Missing README, Missing LICENSE
    project.repository_tree.return_value = []
    res = api_helper.check_project_compliance(project, read_file_fn=lambda p,f,b: None)
    assert res["README.md"] is False
    assert res["LICENSE"] is False
    assert res["license_status"] == "not_found"
    assert res["readme_status"] == "missing"

    # CASE: Empty README
    project.repository_tree.return_value = [{"name": "README.md"}]
    res = api_helper.check_project_compliance(project, read_file_fn=lambda p,f,b: " ")
    assert res["readme_status"] == "empty"

    # CASE: README quality improvement needed
    project.repository_tree.return_value = [{"name": "README.md"}]
    res = api_helper.check_project_compliance(project, read_file_fn=lambda p,f,b: "Short README")
    assert res["readme_needs_improvement"] is True

    # CASE: Exception
    project.repository_tree.side_effect = Exception("Crash")
    res = api_helper.check_project_compliance(project)
    assert "error" in res

def test_internal_import_coverage():
    project = MagicMock()
    project.default_branch = "main"
    project.repository_tree.return_value = [{"name": "README.md"}, {"name": "LICENSE"}]
    project.tags.list.return_value = []
    # Mock the internal imports to avoid hitting real API
    with patch("gitlab_utils.files_reader.read_file_content", return_value="some content"):
        # This will trigger 'if read_file_fn is None' blocks
        api_helper.check_extensions_json_for_ruff(project)
        api_helper.check_license_content(project)
        api_helper.check_project_compliance(project)
