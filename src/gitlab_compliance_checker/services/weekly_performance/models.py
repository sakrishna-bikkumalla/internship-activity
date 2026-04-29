from dataclasses import dataclass, field
from typing import Any, NotRequired, TypedDict


class EventDetail(TypedDict):
    type: str
    title: str
    url: str


class GitLabDailyData(TypedDict):
    mrs: int
    issues: int
    commits: int
    time_spent_seconds: int
    active_hours: list[int]
    events_by_hour: dict[int, list[EventDetail]]


class CorpusDailyData(TypedDict):
    audio_urls: list[dict[str, Any]]


class DailyData(TypedDict):
    gitlab: GitLabDailyData
    corpus: CorpusDailyData


@dataclass
class WeeklyActivity:
    intern_name: str
    gitlab_username: str
    corpus_uid: str
    daily_data: dict[str, DailyData] = field(default_factory=dict)
    total_weekly_time: int = 0
    audio_fetched: bool = False


class InternCSVRow(TypedDict):
    team_name: str
    name: str
    gitlab_username: str
    gitlab_email: str
    corpus_username: str
    global_username: str
    global_email: str
    date_of_joining: str
    college_name: str
    id: NotRequired[int]
    batch_name: NotRequired[str]


def parse_intern_csv(csv_content: bytes) -> list[InternCSVRow]:
    import csv
    import io

    # Decode and handle BOM if present
    content = csv_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))

    # Map input columns to our standardized keys (case-insensitive)
    cols = reader.fieldnames or []
    mapping = {}

    # Define aliases for each field
    aliases = {
        "team_name": ["team name", "team_name", "team"],
        "name": ["name", "full name", "fullname", "full_name", "display name", "display_name"],
        "gitlab_username": ["gitlab_username", "gitlab username", "username", "user", "gitlab user"],
        "gitlab_email": ["gitlab_email", "gitlab email", "email", "mail"],
        "corpus_username": ["corpus_username", "corpus username", "corpus uid", "corpus_uid", "corpus"],
        "global_username": ["global_username", "global username", "global user"],
        "global_email": ["global_email", "global email", "global mail"],
        "date_of_joining": ["date_of_joining", "date of joining", "doj", "joining date", "joining_date"],
        "college_name": ["college_name", "college name", "college", "university", "institution"],
    }

    for f_key, field_aliases in aliases.items():
        for col in cols:
            if col.strip().lower() in field_aliases:
                mapping[f_key] = col
                break

    rows: list[InternCSVRow] = []
    for row in reader:
        parsed: InternCSVRow = {
            "team_name": row.get(mapping.get("team_name", ""), "").strip(),
            "name": row.get(mapping.get("name", ""), "").strip(),
            "gitlab_username": row.get(mapping.get("gitlab_username", ""), "").strip(),
            "gitlab_email": row.get(mapping.get("gitlab_email", ""), "").strip(),
            "corpus_username": row.get(mapping.get("corpus_username", ""), "").strip(),
            "global_username": row.get(mapping.get("global_username", ""), "").strip(),
            "global_email": row.get(mapping.get("global_email", ""), "").strip(),
            "date_of_joining": row.get(mapping.get("date_of_joining", ""), "").strip(),
            "college_name": row.get(mapping.get("college_name", ""), "").strip(),
        }
        # If any of the mandatory ID fields are present, add the row
        if parsed["gitlab_username"] or parsed["name"]:
            rows.append(parsed)
    return rows
