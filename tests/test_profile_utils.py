from gitlab_compliance_checker.services.profile.profile_utils import (
    LOCAL_TZ,
    classify_time_slot,
    format_date_time,
    parse_gitlab_datetime,
    process_commits,
    process_groups,
    split_projects,
)

# ---------------- DATETIME HELPERS ----------------


def test_parse_gitlab_datetime_valid_z():
    """UTC timestamp with 'Z' should be converted to IST."""
    ts = "2024-03-25T10:00:00Z"
    dt = parse_gitlab_datetime(ts)
    assert dt.tzinfo == LOCAL_TZ
    # 10:00 UTC is 15:30 IST
    assert dt.hour == 15
    assert dt.minute == 30


def test_parse_gitlab_datetime_valid_offset():
    """UTC timestamp with '+00:00' should be converted to IST."""
    ts = "2024-03-25T10:00:00+00:00"
    dt = parse_gitlab_datetime(ts)
    assert dt.tzinfo == LOCAL_TZ
    assert dt.hour == 15
    assert dt.minute == 30


def test_parse_gitlab_datetime_naive():
    """Naive timestamp should be treated as UTC then converted to IST."""
    ts = "2024-03-25T10:00:00"
    dt = parse_gitlab_datetime(ts)
    assert dt.tzinfo == LOCAL_TZ
    assert dt.hour == 15
    assert dt.minute == 30


def test_parse_gitlab_datetime_empty():
    """Empty or None timestamp should return None."""
    assert parse_gitlab_datetime("") is None
    assert parse_gitlab_datetime(None) is None


def test_parse_gitlab_datetime_invalid():
    """Invalid timestamp string should return None (exception handling)."""
    assert parse_gitlab_datetime("not-a-date") is None


# ---------------- TIME SLOT CLASSIFICATION ----------------


def test_classify_time_slot_morning():
    """Morning: 09:00 – 12:30 (IST)."""
    # 04:00 UTC = 09:30 IST
    assert classify_time_slot("2024-03-25T04:00:00Z") == "Morning"
    # 07:00 UTC = 12:30 IST (Boundary inclusive)
    assert classify_time_slot("2024-03-25T07:00:00Z") == "Morning"
    # 03:30 UTC = 09:00 IST (Start boundary)
    assert classify_time_slot("2024-03-25T03:30:00Z") == "Morning"


def test_classify_time_slot_afternoon():
    """Afternoon: 14:00 – 17:00 (IST)."""
    # 08:30 UTC = 14:00 IST
    assert classify_time_slot("2024-03-25T08:30:00Z") == "Afternoon"
    # 10:30 UTC = 16:00 IST
    assert classify_time_slot("2024-03-25T10:30:00Z") == "Afternoon"
    # 11:30 UTC = 17:00 IST (End boundary inclusive)
    assert classify_time_slot("2024-03-25T11:30:00Z") == "Afternoon"


def test_classify_time_slot_other():
    """All other times."""
    # 03:29 UTC = 08:59 IST (Before morning)
    assert classify_time_slot("2024-03-25T03:29:59Z") == "Other"
    # 07:01 UTC = 12:31 IST (After morning)
    assert classify_time_slot("2024-03-25T07:01:00Z") == "Other"
    # 08:29 UTC = 13:59 IST (Before afternoon)
    assert classify_time_slot("2024-03-25T08:29:59Z") == "Other"
    # 11:31 UTC = 17:01 IST (After afternoon)
    assert classify_time_slot("2024-03-25T11:31:00Z") == "Other"
    # Night time
    assert classify_time_slot("2024-03-25T20:00:00Z") == "Other"


def test_classify_time_slot_invalid():
    """Invalid/None inputs should return None."""
    assert classify_time_slot("") is None
    assert classify_time_slot(None) is None


# ---------------- FORMAT DATE TIME ----------------


def test_format_date_time_valid():
    """Valid timestamp should return ISO date and 12h time."""
    date_str, time_str = format_date_time("2024-03-25T10:00:00Z")
    assert date_str == "2024-03-25"
    assert time_str == "03:30 PM"


def test_format_date_time_invalid():
    """Invalid/Empty timestamp should return ('-', '-')."""
    assert format_date_time("") == ("-", "-")
    assert format_date_time(None) == ("-", "-")


# ---------------- DATA PROCESSING ----------------


def test_process_commits_normal():
    """Process commit list into structured rows."""
    commits = [
        {
            "created_at": "2024-03-25T04:00:00Z",
            "project_scope": "Internal",
            "project_name": "Project A",
            "title": "Fix bug\n\nMore details",
        },
        {
            "committed_date": "2024-03-25T10:00:00Z",
            "project_scope": "Public",
            "project_name": "Project B",
            "message": "Update README",
        },
    ]
    processed = process_commits(commits)
    assert len(processed) == 2
    assert processed[0]["slot"] == "Morning"
    assert processed[0]["message"] == "Fix bug"
    assert processed[1]["slot"] == "Afternoon"
    assert processed[1]["message"] == "Update README"


def test_process_commits_edge_cases():
    """Empty list, None, and invalid entries."""
    assert process_commits([]) == []
    assert process_commits(None) == []

    # Missing date should skip
    commits = [{"title": "No date"}]
    assert process_commits(commits) == []

    # Missing fields should use defaults
    commits = [{"created_at": "2024-03-25T04:00:00Z"}]
    processed = process_commits(commits)
    assert processed[0]["project_type"] == "-"
    assert processed[0]["project"] == "-"
    assert processed[0]["message"] == ""


def test_process_groups_normal():
    """Process group list into structured rows."""
    groups = [
        {
            "name": "Group A",
            "full_path": "path/a",
            "visibility": "public",
            "web_url": "https://gitlab.com/path/a",
        }
    ]
    processed = process_groups(groups)
    assert len(processed) == 1
    assert processed[0]["name"] == "Group A"
    assert processed[0]["path"] == "path/a"


def test_process_groups_edge_cases():
    """Empty list, None, and missing fields."""
    assert process_groups([]) == []
    assert process_groups(None) == []

    # Missing fields should use defaults
    groups = [{"name": "Only Name"}]
    processed = process_groups(groups)
    assert processed[0]["name"] == "Only Name"
    assert processed[0]["path"] == "-"
    assert processed[0]["visibility"] == "-"
    assert processed[0]["web_url"] == "-"

    # full_path fallback to path
    groups = [{"path": "short-path"}]
    processed = process_groups(groups)
    assert processed[0]["path"] == "short-path"


# ---------------- SPLIT PROJECTS ----------------


def test_split_projects_personal():
    """Projects owned by user should be classified as personal."""
    user_info = {"id": 42, "username": "testuser"}
    projects = [
        {"name": "my-project", "owner": {"id": 42}},
        {"name": "other-project", "owner": {"id": 99}},
    ]
    personal, contributed = split_projects(projects, user_info)
    assert len(personal) == 1
    assert personal[0]["name"] == "my-project"
    assert len(contributed) == 1
    assert contributed[0]["name"] == "other-project"


def test_split_projects_empty():
    """Empty or None project list."""
    user_info = {"id": 1}
    personal, contributed = split_projects([], user_info)
    assert personal == []
    assert contributed == []

    personal, contributed = split_projects(None, user_info)
    assert personal == []
    assert contributed == []


def test_split_projects_no_owner():
    """Projects without owner field should be treated as contributed."""
    user_info = {"id": 1}
    projects = [
        {"name": "no-owner-project"},
        {"owner": {}},
    ]
    personal, contributed = split_projects(projects, user_info)
    assert personal == []
    assert len(contributed) == 2


def test_split_projects_missing_user_id():
    """Missing user_id should use default 0."""
    projects = [
        {"name": "p1", "owner": {"id": 1}},
        {"name": "p2", "owner": {"id": 0}},
    ]
    personal, contributed = split_projects(projects, {"username": "test"})
    assert len(personal) == 1
    assert personal[0]["name"] == "p2"
    assert contributed[0]["name"] == "p1"
