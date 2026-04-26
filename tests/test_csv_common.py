import pytest
from unittest.mock import MagicMock, patch
from gitlab_compliance_checker.ui import csv_common

def test_map_row_to_member():
    # InternCSVRow keys: name, gitlab_username, gitlab_email, etc.
    row = {
        "team_name": "Team A",
        "name": "John Doe",
        "gitlab_username": "jdoe",
        "gitlab_email": "jdoe@example.com",
        "corpus_username": "jdoe_c",
        "college_name": "My College",
        "global_username": "G1",
        "global_email": "g@e.com",
        "date_of_joining": "2024-01-01"
    }
    member = csv_common.map_row_to_member(row)
    assert member["name"] == "John Doe"
    assert member["username"] == "jdoe"
    assert member["email"] == "jdoe@example.com"
    assert member["college"] == "My College"
    assert member["corpus_username"] == "jdoe_c"

def test_group_by_team():
    rows = [
        {"team_name": "Team A", "name": "User 1", "gitlab_username": "u1"},
        {"team_name": "Team B", "name": "User 2", "gitlab_username": "u2"},
        {"team_name": "Team A", "name": "User 3", "gitlab_username": "u3"},
        {"name": "User 4", "gitlab_username": "u4"}, # Missing team name
    ]
    grouped = csv_common.group_by_team(rows)
    assert len(grouped["Team A"]) == 2
    assert len(grouped["Team B"]) == 1
    assert len(grouped["Default Team"]) == 1
    assert grouped["Team A"][0]["username"] == "u1"

class DummyState(dict):
    def __getattr__(self, key): return self.get(key)
    def __setattr__(self, key, value): self[key] = value

@patch("gitlab_compliance_checker.ui.csv_common.st")
def test_render_csv_upload_section_no_file(mock_st):
    mock_st.file_uploader.return_value = None
    rows = csv_common.render_csv_upload_section("test_key")
    assert rows == []
    mock_st.file_uploader.assert_called_once()

@patch("gitlab_compliance_checker.ui.csv_common.st")
@patch("gitlab_compliance_checker.ui.csv_common.parse_intern_csv")
def test_render_csv_upload_section_with_file(mock_parse, mock_st):
    mock_file = MagicMock()
    mock_file.name = "test.csv"
    mock_file.read.return_value = b"some content"
    mock_st.file_uploader.return_value = mock_file
    
    mock_parse.return_value = [{"name": "John", "gitlab_username": "j1"}]
    
    rows = csv_common.render_csv_upload_section("test_key")
    assert len(rows) == 1
    assert rows[0]["name"] == "John"
    mock_st.success.assert_called()

@patch("gitlab_compliance_checker.ui.csv_common.st")
@patch("gitlab_compliance_checker.ui.csv_common.parse_intern_csv")
def test_render_csv_upload_section_error(mock_parse, mock_st):
    mock_file = MagicMock()
    mock_file.name = "test.csv"
    mock_st.file_uploader.return_value = mock_file
    mock_parse.side_effect = Exception("Parse Error")
    
    rows = csv_common.render_csv_upload_section("test_key")
    assert rows == []
    mock_st.error.assert_called()
