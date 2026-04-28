from datetime import date
from unittest.mock import MagicMock, patch

from gitlab_compliance_checker.ui import weekly_performance


def test_fetch_team_audio_urls():
    mock_corpus = MagicMock()
    mock_corpus.fetch_records.return_value = [
        {"file_url": "url1", "file_name": "f1", "created_at": "2024-04-15T10:00:00Z", "media_type": "audio"}
    ]
    mock_corpus.extract_audio_urls.return_value = ["url1"]

    interns = [{"name": "Test", "corpus_username": "uid1"}]
    data = weekly_performance.fetch_team_audio_urls(mock_corpus, interns, "2024-04-15", "2024-04-19")

    assert "uid1" in data
    assert "2024-04-15" in data["uid1"]
    assert data["uid1"]["2024-04-15"][0]["url"] == "url1"


@patch("streamlit.session_state", {"wp_activity_cache": {}})
@patch("streamlit.spinner")
@patch("gitlab_compliance_checker.ui.weekly_performance.fetch_team_audio_urls")
@patch("gitlab_compliance_checker.ui.weekly_performance.aggregate_intern_data")
def test_fetch_all_activity_new(mock_agg, mock_fetch_audio, mock_spinner):
    mock_gl = MagicMock()
    mock_corpus = MagicMock()
    intern = {"name": "Test", "gitlab_username": "user", "corpus_username": "uid"}
    start = date(2024, 4, 15)

    # Mocking aggregate_intern_data return
    mock_activity = MagicMock()
    mock_activity.daily_data = {}
    mock_activity.total_weekly_time = 0
    mock_agg.return_value = mock_activity

    mock_fetch_audio.return_value = {"uid": {"2024-04-15": [{"url": "url1"}]}}

    # We must patch session_state in the module where it's used
    with patch(
        "gitlab_compliance_checker.ui.weekly_performance.st.session_state", {"wp_activity_cache": {}}
    ) as mock_state:
        # Pass 7 for num_days and mock_corpus for corpus_client
        activity = weekly_performance._fetch_all_activity(mock_gl, intern, start, 7, mock_corpus)
        assert activity.intern_name == "Test"
        assert activity.audio_fetched is True
        # The cache key is now (start_date_iso, num_days, gitlab_username)
        assert (start.isoformat(), 7, "user") in mock_state["wp_activity_cache"]


def test_parse_intern_csv_integration():
    from gitlab_compliance_checker.services.weekly_performance.models import parse_intern_csv

    content = b"Team Name,Full Name,GitLab Username,Corpus UID\nBackend,John Doe,jdo,juid"
    rows = parse_intern_csv(content)
    assert len(rows) == 1
    assert rows[0]["name"] == "John Doe"
