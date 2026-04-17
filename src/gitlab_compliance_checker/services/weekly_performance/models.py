from dataclasses import dataclass, field
from typing import TypedDict


class GitLabDailyData(TypedDict):
    mrs: int
    issues: int
    commits: int
    time_spent_seconds: int


class CorpusDailyData(TypedDict):
    audio_urls: list[str]


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


class InternCSVRow(TypedDict):
    team_name: str
    full_name: str
    gitlab_username: str
    corpus_uid: str


def parse_intern_csv(csv_content: bytes) -> list[InternCSVRow]:
    import csv
    import io

    reader = csv.DictReader(io.StringIO(csv_content.decode("utf-8")))
    rows: list[InternCSVRow] = []
    for row in reader:
        rows.append(
            InternCSVRow(
                team_name=row.get("Team Name", "").strip(),
                full_name=row.get("Full Name", "").strip(),
                gitlab_username=row.get("GitLab Username", "").strip(),
                corpus_uid=row.get("Corpus UID", "").strip(),
            )
        )
    return rows
