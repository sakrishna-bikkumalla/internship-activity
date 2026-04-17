from collections import defaultdict
from datetime import date

from gitlab_compliance_checker.services.weekly_performance.models import (
    CorpusDailyData,
    DailyData,
    GitLabDailyData,
    WeeklyActivity,
)


def _get_user_id(gl_client, username: str) -> int | None:
    u_data = gl_client._get("/users", params={"username": username})
    target_user = next(
        (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(username).lower()),
        None,
    )
    return target_user["id"] if target_user else None


def _fetch_mrs_by_date(gl_client, user_id: int, start_date: date, end_date: date) -> dict[str, int]:
    mrs = gl_client._get(
        "/merge_requests",
        params={
            "author_id": user_id,
            "scope": "all",
            "created_after": start_date.isoformat(),
            "created_before": end_date.isoformat(),
        },
    )
    counts: dict[str, int] = defaultdict(int)
    for mr in mrs or []:
        created_at = mr.get("created_at", "")
        if created_at:
            date_str = created_at[:10]
            counts[date_str] += 1
    return dict(counts)


def _fetch_issues_by_date(gl_client, user_id: int, start_date: date, end_date: date) -> dict[str, int]:
    authored = gl_client._get(
        "/issues",
        params={
            "author_id": user_id,
            "scope": "all",
            "created_after": start_date.isoformat(),
            "created_before": end_date.isoformat(),
        },
    )
    assigned = gl_client._get(
        "/issues",
        params={
            "assignee_id": user_id,
            "scope": "all",
            "created_after": start_date.isoformat(),
            "created_before": end_date.isoformat(),
        },
    )
    counts: dict[str, int] = defaultdict(int)
    seen_ids = set()
    for issues, _role in [(authored or [], "author"), (assigned or [], "assignee")]:
        for issue in issues:
            issue_id = issue.get("id")
            if issue_id in seen_ids:
                continue
            seen_ids.add(issue_id)
            created_at = issue.get("created_at", "")
            if created_at:
                date_str = created_at[:10]
                counts[date_str] += 1
    return dict(counts)


def _fetch_commits_by_date(
    gl_client, user_id: int, project_ids: list[int] | None, start_date: date, end_date: date
) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    if not project_ids:
        return dict(counts)

    for pid in project_ids:
        commits = gl_client._get(
            f"/projects/{pid}/repository/commits",
            params={"author_id": user_id, "since": start_date.isoformat(), "until": end_date.isoformat()},
        )
        for commit in commits or []:
            created_at = commit.get("created_at", "")
            if created_at:
                date_str = created_at[:10]
                counts[date_str] += 1
    return dict(counts)


def aggregate_intern_data(
    gl_client,
    gitlab_username: str,
    corpus_uid: str,
    intern_name: str,
    start_date: date,
    end_date: date,
    project_ids: list[int] | None = None,
) -> WeeklyActivity:
    """Aggregate all GitLab activity for one intern into WeeklyActivity model."""
    user_id = _get_user_id(gl_client, gitlab_username)
    if not user_id:
        return WeeklyActivity(intern_name=intern_name, gitlab_username=gitlab_username, corpus_uid=corpus_uid)

    from gitlab_compliance_checker.infrastructure.gitlab.timelogs import aggregate_daily_time, fetch_user_timelogs

    timelogs = fetch_user_timelogs(gl_client, gitlab_username, start_date, end_date)
    daily_times = aggregate_daily_time(timelogs)

    mr_counts = _fetch_mrs_by_date(gl_client, user_id, start_date, end_date)
    issue_counts = _fetch_issues_by_date(gl_client, user_id, start_date, end_date)
    commit_counts = _fetch_commits_by_date(gl_client, user_id, project_ids, start_date, end_date)

    all_dates: set[str] = set()
    all_dates.update(daily_times.keys())
    all_dates.update(mr_counts.keys())
    all_dates.update(issue_counts.keys())
    all_dates.update(commit_counts.keys())

    daily_data: dict[str, DailyData] = {}
    total_weekly_time = 0

    for date_str in sorted(all_dates):
        gitlab: GitLabDailyData = {
            "mrs": mr_counts.get(date_str, 0),
            "issues": issue_counts.get(date_str, 0),
            "commits": commit_counts.get(date_str, 0),
            "time_spent_seconds": daily_times.get(date_str, 0),
        }
        corpus: CorpusDailyData = {"audio_urls": []}

        daily_data[date_str] = DailyData(gitlab=gitlab, corpus=corpus)
        total_weekly_time += daily_times.get(date_str, 0)

    return WeeklyActivity(
        intern_name=intern_name,
        gitlab_username=gitlab_username,
        corpus_uid=corpus_uid,
        daily_data=daily_data,
        total_weekly_time=total_weekly_time,
    )


def aggregate_batch_interns(
    gl_client,
    intern_rows: list[dict[str, str]],
    start_date: date,
    end_date: date,
    project_ids: list[int] | None = None,
) -> list[WeeklyActivity]:
    """Aggregate GitLab activity for multiple interns."""
    results: list[WeeklyActivity] = []
    for row in intern_rows:
        activity = aggregate_intern_data(
            gl_client,
            gitlab_username=row.get("gitlab_username", ""),
            corpus_uid=row.get("corpus_uid", ""),
            intern_name=row.get("full_name", ""),
            start_date=start_date,
            end_date=end_date,
            project_ids=project_ids,
        )
        results.append(activity)
    return results
