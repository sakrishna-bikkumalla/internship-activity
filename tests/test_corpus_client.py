import pytest
from unittest.mock import patch, MagicMock
from gitlab_compliance_checker.infrastructure.corpus.client import CorpusClient


def test_corpus_login_success():
    with patch("requests.post") as mock_post:
        mock_post.return_value.json.return_value = {"access_token": "test_token"}
        mock_post.return_value.status_code = 200
        client = CorpusClient()
        token = client.login("+1234567890", "password")
        assert token == "test_token"
        assert client.token == "test_token"


def test_extract_audio_urls():
    records = [
        {"date": "2024-01-01", "file_url": "https://example.com/audio1.mp3"},
        {"date": "2024-01-01", "file_url": "https://example.com/audio2.mp3"},
        {"date": "2024-01-02", "file_url": ""},
        {"date": "2024-01-03"},
    ]
    client = CorpusClient()
    urls = client.extract_audio_urls(records)
    assert urls == ["https://example.com/audio1.mp3", "https://example.com/audio2.mp3"]


def test_fetch_records_success():
    with patch("requests.get") as mock_get:
        user_response = MagicMock()
        user_response.json.return_value = {"id": "915b4d14-dca6-4c40-a59c-62226481357b", "username": "user123"}
        user_response.raise_for_status.return_value = None

        records_response = MagicMock()
        records_response.json.return_value = [{"id": "1", "date": "2024-01-01", "file_url": "url1"}]
        records_response.raise_for_status.return_value = None

        mock_get.side_effect = [user_response, records_response]
        client = CorpusClient()
        client.token = "fake_token"
        records = client.fetch_records("user123", "2024-01-01", "2024-01-07")
        assert len(records) == 1
        assert records[0]["file_url"] == "url1"
        assert mock_get.call_count == 2
