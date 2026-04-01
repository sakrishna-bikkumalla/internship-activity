from unittest.mock import MagicMock, patch

import pytest
from gitlab import GitlabGetError

from modes import compliance_mode


@pytest.fixture
def mock_project():
    m = MagicMock()
    m.default_branch = "main"
    return m


@pytest.fixture
def mock_client():
    return MagicMock()


def test_read_file_content_success(mock_project):
    compliance_mode.read_file_content.clear()
    file_mock = MagicMock()
    file_mock.decode.return_value = b"hello"
    mock_project.files.get.return_value = file_mock
    res = compliance_mode.read_file_content(mock_project, "f.txt", "main")
    assert res == "hello"


def test_read_file_content_fail(mock_project):
    compliance_mode.read_file_content.clear()
    mock_project.files.get.side_effect = Exception("error")
    assert compliance_mode.read_file_content(mock_project, "f.txt", "main2") is None


def test_check_vscode_settings(mock_project):
    mock_project.repository_tree.return_value = [{"name": "settings.json"}]
    assert compliance_mode.check_vscode_settings(mock_project) is True

    mock_project.repository_tree.side_effect = Exception("404")
    assert compliance_mode.check_vscode_settings(mock_project) is False


def test_check_license_content_agpl(mock_project):
    with patch("modes.compliance_mode.read_file_content") as mock_read:
        # AGPLv3
        mock_read.return_value = "Affero General Public License version 3 19 November 2007"
        assert compliance_mode.check_license_content(mock_project) == "valid"


def test_check_license_content_gplv3(mock_project):
    with patch("modes.compliance_mode.read_file_content") as mock_read:
        # GPLv3
        mock_read.return_value = "General Public License version 3 29 June 2007"
        assert compliance_mode.check_license_content(mock_project) == "gnu_other"


def test_check_license_content_invalid(mock_project):
    with patch("modes.compliance_mode.read_file_content") as mock_read:
        mock_read.return_value = "MIT License"
        assert compliance_mode.check_license_content(mock_project) == "invalid"

        mock_read.return_value = None
        assert compliance_mode.check_license_content(mock_project) == "not_found"


def test_check_extensions_json_for_ruff(mock_project):
    with patch("modes.compliance_mode.read_file_content") as mock_read:
        mock_read.return_value = '{"recommendations": ["charliermarsh.ruff"]}'
        assert compliance_mode.check_extensions_json_for_ruff(mock_project) is True

        mock_read.return_value = "bad json"
        assert compliance_mode.check_extensions_json_for_ruff(mock_project) is False


def test_check_project_compliance_comprehensive(mock_project):
    mock_project.repository_tree.return_value = [
        {"name": "README.md"},
        {"name": "LICENSE"},
        {"name": ".gitignore"},
        {"name": "pyproject.toml"},
        {"name": "uv.lock"},
    ]
    mock_project.description = "Test Project"
    mock_project.tags.list.return_value = ["v1.0"]

    with patch("modes.compliance_mode.read_file_content", return_value="README content with Installation"):
        with patch("modes.compliance_mode.check_license_content", return_value="valid"):
            report = compliance_mode.check_project_compliance(mock_project)
            assert report["README.md"] is True
            assert report["license_valid"] is True
            assert report["description_present"] is True


def test_extract_path_from_url():
    assert compliance_mode.extract_path_from_url("https://gitlab.com/gp/p1.git") == "gp/p1"
    assert compliance_mode.extract_path_from_url("gp/p2") == "gp/p2"


def test_render_project_compliance_ui():
    report = {"README.md": True, "license_valid": True, "readme_status": "present"}
    with patch("streamlit.markdown") as mock_md:
        compliance_mode.render_project_compliance_ui(report)
        assert mock_md.call_count >= 1


def test_get_project_with_retries_fail(mock_client):
    err = GitlabGetError()
    err.response = MagicMock(status_code=404)
    mock_client.projects.get.side_effect = err
    with pytest.raises(GitlabGetError):
        compliance_mode.get_project_with_retries(mock_client, "bad/repo")


def test_check_project_compliance_missing(mock_project):
    mock_project.repository_tree.return_value = []
    with patch("modes.compliance_mode.read_file_content", return_value=None):
        report = compliance_mode.check_project_compliance(mock_project)
        assert report["README.md"] is False


def test_render_compliance_mode_batch_flow(mock_client):
    with patch("streamlit.tabs") as mock_tabs:
        tab1, tab2 = MagicMock(), MagicMock()
        mock_tabs.return_value = [tab1, tab2]
        # In tab2 (Batch)
        with patch("streamlit.text_area", return_value="gp/p1"):
            with patch("streamlit.button", return_value=True):
                with patch("modes.compliance_mode.get_project_with_retries") as mock_get:
                    proj = MagicMock()
                    proj.name_with_namespace = "GP / P1"
                    mock_get.return_value = proj
                    with patch(
                        "modes.compliance_mode.check_project_compliance", return_value={"readme_status": "present"}
                    ):
                        with patch("streamlit.dataframe"):
                            with patch("streamlit.progress"):
                                compliance_mode.render_compliance_mode(mock_client)


def test_compliance_utils(mock_project):
    mock_project.repository_tree.return_value = [{"name": "settings.json"}]
    assert compliance_mode.check_vscode_file_exists(mock_project, "settings.json") is True

    with patch("modes.compliance_mode.read_file_content", return_value='{"ruff.lint.enable": true}'):
        res = compliance_mode.check_vscode_settings_content(mock_project)
        assert isinstance(res, dict)
        assert res.get("exists") is True

    mock_project.branches.list.return_value = [MagicMock(name="main")]
    assert len(compliance_mode.get_project_branches(mock_project)) == 1


def test_get_suggestions():
    with patch("streamlit.markdown") as mock_md:
        compliance_mode.get_suggestions_for_missing_items({"readme_status": "missing"})
        assert mock_md.call_count > 0


def test_check_license_edge_cases(mock_project):
    with patch("modes.compliance_mode.read_file_content", return_value="bad content"):
        assert compliance_mode.check_license_content(mock_project) == "invalid"


def test_render_batch_project_compliance_internal(mock_client):
    with patch("modes.compliance_mode.get_project_with_retries") as mock_get:
        proj = MagicMock()
        proj.name_with_namespace = "P1"
        mock_get.return_value = proj
        with patch(
            "modes.compliance_mode.check_project_compliance",
            return_value={"readme_status": "present", "license_valid": True},
        ):
            with patch("streamlit.progress"):
                with patch("streamlit.dataframe"):
                    compliance_mode.render_batch_project_compliance_internal(mock_client)


def test_render_project_compliance_ui_negative():
    report = {
        "readme_status": "missing",
        "license_valid": False,
        "gitignore": False,
        "pyproject_toml": False,
        "uv_lock": False,
        "description_present": False,
        "tags_present": False,
        "vscode_settings": False,
        "vscode_extensions": False,
        "templates": False,
    }
    with patch("streamlit.markdown") as mock_md:
        compliance_mode.render_project_compliance_ui(report)
        assert mock_md.call_count > 0
