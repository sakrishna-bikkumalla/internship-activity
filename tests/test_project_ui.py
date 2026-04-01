from unittest.mock import MagicMock, patch

import pytest

from Projects.project_ui import render_project_compliance, render_project_section


@pytest.fixture
def mock_gl():
    return MagicMock()


class DummyColumn:
    def __init__(self):
        self.metric = MagicMock()
        self.write = MagicMock()
        self.markdown = MagicMock()
        self.caption = MagicMock()
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
        mock_st.write = MagicMock()
        mock_st.tabs = MagicMock(return_value=[DummyColumn()] * 5)
        mock_st.columns = MagicMock(return_value=[DummyColumn()] * 4)
        mock_st.spinner = MagicMock()
        mock_st.spinner.return_value.__enter__ = MagicMock()
        mock_st.spinner.return_value.__exit__ = MagicMock()
        mock_st.expander = MagicMock()
        mock_st.expander.return_value.__enter__ = MagicMock()
        mock_st.expander.return_value.__exit__ = MagicMock()
        mock_st.success = MagicMock()
        yield mock_st


class TestRenderProjectCompliance:
    """Tests for render_project_compliance function."""

    @patch("Projects.project_ui.run_project_compliance_checks")
    @patch("Projects.project_ui.get_dx_suggestions")
    def test_renders_metrics(self, mock_suggestions, mock_run_checks, mock_gl, mock_streamlit):
        """Test that metrics are rendered."""
        mock_run_checks.return_value = {
            "dx_score": 85,
            "tools": {"project_type": "Python", "quality_tools": {}, "security": {}, "testing": {}, "automation": {}},
            "license": {"valid": True},
            "readme": {"needs_improvement": False},
            "metadata": {},
            "dx_ci": None,
        }
        mock_suggestions.return_value = []

        render_project_compliance(mock_gl, 123)

        mock_streamlit.subheader.assert_called()
        # st.metric is called inside columns context
        mock_streamlit.columns.assert_called_with(4)
        mock_streamlit.tabs.assert_called()


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
