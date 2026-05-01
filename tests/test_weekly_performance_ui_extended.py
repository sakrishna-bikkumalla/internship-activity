from datetime import date
from unittest.mock import MagicMock, patch

import pytest
import streamlit as st

from gitlab_compliance_checker.ui import weekly_performance


@pytest.fixture
def mock_intern():
    return {
        "team_name": "Team A",
        "name": "John Doe",
        "gitlab_username": "jdoe",
        "gitlab_email": "jdoe@example.com",
        "corpus_username": "jdoec",
        "college_name": "Uni",
    }


def test_init_state():
    with patch("streamlit.session_state", {}):
        weekly_performance._init_state()
        assert "wp_view_mode" in st.session_state


@patch("streamlit.date_input")
def test_render_date_selector_single(mock_date):
    mock_date.return_value = date(2024, 1, 1)
    with patch("streamlit.radio", return_value="Single Day"):
        res, mode = weekly_performance._render_date_selector()
        assert mode == "Single Day"
        assert res == date(2024, 1, 1)


@patch("streamlit.selectbox")
def test_render_intern_selector(mock_selectbox, mock_intern):
    mock_selectbox.return_value = "John Doe (@jdoe)"
    interns = [mock_intern]
    selected = weekly_performance._render_intern_selector(interns)
    assert selected["gitlab_username"] == "jdoe"


def test_render_performance_grid_empty():
    with patch("streamlit.markdown"), \
         patch("streamlit.columns", return_value=[MagicMock(), MagicMock()]):
        weekly_performance._render_performance_grid(date(2024, 1, 1), None, num_days=1)
        # Should run without error
