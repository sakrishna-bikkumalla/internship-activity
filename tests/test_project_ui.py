from unittest.mock import MagicMock, patch

import pytest

from Projects.project_ui import get_project_compliance, render_project_compliance, render_project_section


@pytest.fixture
def mock_gl():
    return MagicMock()


class DummyColumn:
    def __init__(self):
        self.metric = MagicMock()
        self.__enter__ = MagicMock(return_value=self)
        self.__exit__ = MagicMock(return_value=False)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


@pytest.fixture
def mock_streamlit():
    with patch("Projects.project_ui.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.json = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.text_input = MagicMock(return_value="")
        mock_st.button = MagicMock(return_value=False)
        mock_st.warning = MagicMock()
        mock_st.error = MagicMock()
        mock_st.columns = MagicMock(return_value=(DummyColumn(), DummyColumn()))
        yield mock_st


class TestGetProjectCompliance:
    """Tests for get_project_compliance function."""

    @patch("Projects.project_ui.check_templates")
    @patch("Projects.project_ui.check_license")
    @patch("Projects.project_ui.check_readme")
    @patch("Projects.project_ui.classify_files")
    def test_returns_all_checks(self, mock_classify, mock_readme, mock_license, mock_templates, mock_gl):
        """Test that all compliance checks are returned."""
        mock_classify.return_value = {"py": 5}
        mock_readme.return_value = {"exists": True, "status": "README present"}
        mock_license.return_value = {"exists": True, "status": "LICENSE present"}
        mock_templates.return_value = {"exists": True, "status": "Templates present"}

        result = get_project_compliance(mock_gl, 123)

        assert "readme" in result
        assert "license" in result
        assert "templates" in result
        assert "file_types" in result

    @patch("Projects.project_ui.check_templates")
    @patch("Projects.project_ui.check_license")
    @patch("Projects.project_ui.check_readme")
    @patch("Projects.project_ui.classify_files")
    def test_missing_readme(self, mock_classify, mock_readme, mock_license, mock_templates, mock_gl):
        """Test handling of missing README."""
        mock_classify.return_value = {}
        mock_readme.return_value = {"exists": False, "status": "Missing README"}
        mock_license.return_value = {"exists": True}
        mock_templates.return_value = {"exists": True}

        result = get_project_compliance(mock_gl, 123)

        assert result["readme"]["exists"] is False


class TestRenderProjectCompliance:
    """Tests for render_project_compliance function."""

    @patch("Projects.project_ui.get_project_compliance")
    def test_renders_metrics(self, mock_get_compliance, mock_gl, mock_streamlit):
        """Test that metrics are rendered."""
        mock_get_compliance.return_value = {
            "readme": {"status": "README present"},
            "license": {"status": "LICENSE present"},
            "templates": {"status": "Templates present"},
            "file_types": {"py": 5},
        }

        render_project_compliance(mock_gl, 123)

        mock_streamlit.subheader.assert_called()
        mock_streamlit.metric.assert_called()
        mock_streamlit.json.assert_called()


class TestRenderProjectSection:
    """Tests for render_project_section function."""

    def test_no_project_ref(self, mock_streamlit):
        """Test warning when no project reference entered."""
        mock_streamlit.button.return_value = True
        mock_streamlit.text_input.return_value = ""

        render_project_section("https://gitlab.com", "token")

        mock_streamlit.warning.assert_called_with("Please enter a valid project ID or path.")

    def test_button_not_clicked(self, mock_streamlit):
        """Test no action when button not clicked."""
        mock_streamlit.button.return_value = False

        render_project_section("https://gitlab.com", "token")

        mock_streamlit.error.assert_not_called()
        mock_streamlit.warning.assert_not_called()

    @patch("gitlab.Gitlab")
    def test_invalid_project(self, mock_gitlab, mock_streamlit):
        """Test error handling for invalid project."""
        mock_streamlit.button.return_value = True
        mock_streamlit.text_input.return_value = "invalid/project"

        mock_gl = MagicMock()
        mock_gl.projects.get.side_effect = Exception("Not Found")
        mock_gitlab.return_value = mock_gl

        render_project_section("https://gitlab.com", "token")

        mock_streamlit.error.assert_called()
