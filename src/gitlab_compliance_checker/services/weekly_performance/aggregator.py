import logging
from collections import defaultdict
from datetime import date, timedelta, timezone

import dateutil.parser

from gitlab_compliance_checker.infrastructure.gitlab import commits, users
from gitlab_compliance_checker.infrastructure.gitlab import projects as gitlab_projects
from gitlab_compliance_checker.services.weekly_performance.models import (
    CorpusDailyData,
    DailyData,
    GitLabDailyData,
    WeeklyActivity,
)

IST = timezone(timedelta(hours=5, minutes=30))


def _parse_ist_date(timestamp: str) -> str:
    """Parse an ISO timestamp and return IST date string YYYY-MM-DD."""
    if not timestamp:
        return ""
    try:
        dt = dateutil.parser.isoparse(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_ist = dt.astimezone(IST)
        return dt_ist.strftime("%Y-%m-%d")
    except Exception:
        return timestamp[:10]


logger = logging.getLogger(__name__)


def _get_user_id(gl_client, username: str) -> int | None:
    u_data = gl_client._get("/users", params={"username": username})
    target_user = next(
        (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(username).lower()),
        None,
    )
    return target_user["id"] if target_user else None


def _fetch_mrs_by_date(gl_client, user_id: int, start_date: date, end_date: date) -> dict[str, int]:
    logger.debug(f"[GitLab] Fetching merged MRs for user_id={user_id}, {start_date} to {end_date}")
    counts: dict[str, int] = defaultdict(int)
    seen_ids: set[int] = set()

    # To find MRs merged this week, we query for merged state and recent updates.
    # An MR merge is an update, so updated_after ensures we catch them.
    date_params = {
        "scope": "all",
        "state": "merged",
        "updated_after": (start_date - timedelta(days=1)).isoformat(),
    }

    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()

    for params, role in [
        ({"author_id": user_id, **date_params}, "author"),
        ({"assignee_id": user_id, **date_params}, "assignee"),
    ]:
        mrs = gl_client._get_paginated("/merge_requests", params=params, max_pages=10) or []
        logger.debug(f"[GitLab] Got {len(mrs)} {role} merged MRs (possibly including older updates)")
        for mr in mrs:
            mr_id = mr.get("id")
            if mr_id in seen_ids:
                continue
            seen_ids.add(mr_id)

            merged_at = mr.get("merged_at", "")
            if merged_at:
                date_str = _parse_ist_date(merged_at)
                # Verify the merge date falls exactly within our target week range
                if start_date_str <= date_str <= end_date_str:
                    counts[date_str] += 1

    logger.debug(f"[GitLab] Merged MRs by date: {dict(counts)}")
    return dict(counts)


def _fetch_issues_by_date(gl_client, user_id: int, start_date: date, end_date: date) -> dict[str, int]:
    logger.debug(f"[GitLab] Fetching assigned issues for user_id={user_id}, {start_date} to {end_date}")
    date_params = {
        "scope": "all",
        "created_after": start_date.isoformat(),
        "created_before": (end_date + timedelta(days=1)).isoformat(),
    }
    assigned = gl_client._get_paginated("/issues", params={"assignee_id": user_id, **date_params}, max_pages=10) or []
    logger.debug(f"[GitLab] Got {len(assigned)} assigned issues")
    counts: dict[str, int] = defaultdict(int)
    for issue in assigned:
        created_at = issue.get("created_at", "")
        if created_at:
            date_str = _parse_ist_date(created_at)
            if date_str:
                counts[date_str] += 1
    logger.debug(f"[GitLab] Issues by date: {dict(counts)}")
    return dict(counts)


def _fetch_commits_by_date(
    gl_client, user_id: int, gitlab_username: str, start_date: date, end_date: date
) -> dict[str, int]:
    logger.debug(
        f"[GitLab] Fetching commits for user_id={user_id}, gitlab_username={gitlab_username}, {start_date} to {end_date}"
    )
    counts: dict[str, int] = defaultdict(int)

    user_obj = users.get_user_by_username(gl_client, gitlab_username)
    if not user_obj:
        logger.debug(f"[GitLab] Could not find user object for {gitlab_username}")
        return dict(counts)

    user_projects = gitlab_projects.get_user_projects(gl_client, user_id, gitlab_username)
    all_projs = user_projects.get("all", [])
    if not all_projs:
        logger.debug(f"[GitLab] No projects found for user {gitlab_username}")
        return dict(counts)

    logger.debug(f"[GitLab] Fetching commits across {len(all_projs)} projects")
    # Broaden range to ensure we capture commits occurring on the end_date across timezones
    api_until = (end_date + timedelta(days=1)).isoformat()
    all_commits, _, _ = commits.get_user_commits(
        gl_client, user_obj, all_projs, since=start_date.isoformat(), until=api_until
    )

    for commit in all_commits or []:
        commit_date = commit.get("date", "")
        if commit_date and commit_date != "N/A":
            counts[commit_date] += 1

    logger.debug(f"[GitLab] Commits by date: {dict(counts)}")
    return dict(counts)


def aggregate_intern_data(
    gl_client,
    gitlab_username: str,
    corpus_uid: str,
    intern_name: str,
    start_date: date,
    end_date: date,
) -> WeeklyActivity:
    """Aggregate all GitLab activity for one intern into WeeklyActivity model."""
    logger.debug(
        f"[Aggregator] aggregate_intern_data for {intern_name} ({gitlab_username}) from {start_date} to {end_date}"
    )
    user_id = _get_user_id(gl_client, gitlab_username)
    if not user_id:
        logger.warning(f"[Aggregator] Could not find GitLab user_id for {gitlab_username}")
        return WeeklyActivity(intern_name=intern_name, gitlab_username=gitlab_username, corpus_uid=corpus_uid)

    from gitlab_compliance_checker.infrastructure.gitlab.timelogs import aggregate_daily_time, fetch_user_timelogs

    logger.debug(f"[Aggregator] Fetching timelogs for {gitlab_username}")
    timelogs = fetch_user_timelogs(gl_client, gitlab_username, start_date, end_date)
    logger.debug(f"[Aggregator] Got {len(timelogs)} timelogs")
    daily_times = aggregate_daily_time(timelogs)

    mr_counts = _fetch_mrs_by_date(gl_client, user_id, start_date, end_date)
    issue_counts = _fetch_issues_by_date(gl_client, user_id, start_date, end_date)
    commit_counts = _fetch_commits_by_date(gl_client, user_id, gitlab_username, start_date, end_date)

    all_dates: set[str] = set()
    all_dates.update(daily_times.keys())
    all_dates.update(mr_counts.keys())
    all_dates.update(issue_counts.keys())
    all_dates.update(commit_counts.keys())
    logger.debug(f"[Aggregator] All dates with activity: {all_dates}")

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

    logger.debug(f"[Aggregator] Finished aggregating data for {intern_name}, total_weekly_time={total_weekly_time}")
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
        )
        results.append(activity)
    return results
