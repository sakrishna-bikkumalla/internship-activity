from unittest.mock import MagicMock, patch

import pytest

from gitlab_compliance_checker.ui.compliance import render_project_compliance_details


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
    with patch("gitlab_compliance_checker.ui.compliance.st") as mock_st:
        mock_st.subheader = MagicMock()
        mock_st.metric = MagicMock()
        mock_st.json = MagicMock()
        mock_st.markdown = MagicMock()
        mock_st.text_input = MagicMock(return_value="")
        mock_st.button = MagicMock(return_value=False)
        mock_st.warning = MagicMock()
        mock_st.error = MagicMock()
        mock_st.write = MagicMock()
        mock_st.tabs = MagicMock(return_value=[DummyColumn()] * 6)
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
    """Tests for render_project_compliance_details function."""

    @patch("gitlab_compliance_checker.ui.compliance.get_dx_suggestions")
    def test_renders_metrics(self, mock_suggestions, mock_gl, mock_streamlit):
        """Test that metrics are rendered."""
        report = {
            "dx_score": 85,
            "tools": {"project_type": "Python", "quality_tools": {}, "security": {}, "testing": {}, "automation": {}},
            "license": {"valid": True},
            "readme": {"needs_improvement": False},
            "metadata": {},
            "dx_ci": None,
        }
        mock_suggestions.return_value = []

        render_project_compliance_details(report)

        # st.metric is called inside columns context
        mock_streamlit.columns.assert_called_with(4)
        mock_streamlit.tabs.assert_called()
