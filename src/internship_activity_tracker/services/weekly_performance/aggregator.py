import logging
from collections import defaultdict
from datetime import date, timedelta, timezone

import dateutil.parser

from internship_activity_tracker.infrastructure.gitlab import commits, users
from internship_activity_tracker.infrastructure.gitlab import projects as gitlab_projects
from internship_activity_tracker.services.weekly_performance.models import (
    CorpusDailyData,
    DailyData,
    EventDetail,
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
        if "T" in timestamp:
            return timestamp.split("T")[0]
        return timestamp[:10]


def _get_ist_hour(timestamp: str) -> int | None:
    """Parse an ISO timestamp and return IST hour (0-23)."""
    if not timestamp:
        return None
    try:
        dt = dateutil.parser.isoparse(timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_ist = dt.astimezone(IST)
        return dt_ist.hour
    except Exception:
        return None


logger = logging.getLogger(__name__)


def _get_user_id(gl_client, username: str) -> int | None:
    u_data = gl_client._get("/users", params={"username": username})
    target_user = next(
        (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(username).lower()),
        None,
    )
    return target_user["id"] if target_user else None


_RawMRResult = tuple[
    dict[str, int],
    dict[str, set[int]],
    dict[str, dict[int, list[EventDetail]]],
    list[dict],
]


def _fetch_mrs_by_date(gl_client, user_id: int, start_date: date, end_date: date) -> _RawMRResult:
    """Fetch merged MRs. Returns (counts, active_hours, events, raw_mr_list)."""
    logger.debug(f"[GitLab] Fetching merged MRs for user_id={user_id}, {start_date} to {end_date}")
    counts: dict[str, int] = defaultdict(int)
    active_hours: dict[str, set[int]] = defaultdict(set)
    events: dict[str, dict[int, list[EventDetail]]] = defaultdict(lambda: defaultdict(list))
    seen_ids: set[int] = set()
    raw_mrs: list[dict] = []

    date_params = {
        "scope": "all",
        "state": "all",
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
            raw_mrs.append(mr)

            # Use merged_at, closed_at, or updated_at for activity attribution
            act_timestamp = mr.get("merged_at") or mr.get("closed_at") or mr.get("updated_at", "")
            if act_timestamp:
                date_str = _parse_ist_date(act_timestamp)
                if start_date_str <= date_str <= end_date_str:
                    counts[date_str] += 1
                    hour = _get_ist_hour(act_timestamp)
                    if hour is not None:
                        active_hours[date_str].add(hour)
                        # Add state to title for clarity in UI events
                        state = mr.get("state", "opened").capitalize()
                        title = f"[{state}] {mr.get('title', '')}"
                        events[date_str][hour].append(
                            {"type": "mr", "title": title, "url": mr.get("web_url", ""), "timestamp": act_timestamp}
                        )

    logger.debug(f"[GitLab] Merged MRs by date: {dict(counts)}")
    return dict(counts), dict(active_hours), dict(events), raw_mrs


def _fetch_issues_by_date(
    gl_client, user_id: int, start_date: date, end_date: date
) -> tuple[dict[str, int], dict[str, set[int]], dict[str, dict[int, list[EventDetail]]], list[dict]]:
    """Fetch assigned issues. Returns (counts, active_hours, events, raw_issue_list)."""
    logger.debug(f"[GitLab] Fetching assigned issues for user_id={user_id}, {start_date} to {end_date}")
    date_params = {
        "scope": "all",
        "state": "all",
        "updated_after": (start_date - timedelta(days=1)).isoformat(),
    }
    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()
    assigned = gl_client._get_paginated("/issues", params={"assignee_id": user_id, **date_params}, max_pages=10) or []
    logger.debug(f"[GitLab] Got {len(assigned)} assigned issues")
    counts: dict[str, int] = defaultdict(int)
    active_hours: dict[str, set[int]] = defaultdict(set)
    events: dict[str, dict[int, list[EventDetail]]] = defaultdict(lambda: defaultdict(list))

    for issue in assigned:
        # Use closed_at if available (for closed issues), else created_at
        act_timestamp = issue.get("closed_at") or issue.get("created_at", "")
        if act_timestamp:
            date_str = _parse_ist_date(act_timestamp)
            if date_str and start_date_str <= date_str <= end_date_str:
                counts[date_str] += 1
                hour = _get_ist_hour(act_timestamp)
                if hour is not None:
                    active_hours[date_str].add(hour)
                    # Add state to title for clarity
                    state = issue.get("state", "opened").capitalize()
                    title = f"[{state}] {issue.get('title', '')}"
                    events[date_str][hour].append(
                        {"type": "issue", "title": title, "url": issue.get("web_url", ""), "timestamp": act_timestamp}
                    )

    logger.debug(f"[GitLab] Issues by date: {dict(counts)}")
    return dict(counts), dict(active_hours), dict(events), assigned


def _fetch_commits_by_date(
    gl_client,
    user_id: int,
    gitlab_username: str,
    start_date: date,
    end_date: date,
    override_email: str | None = None,
    override_username: str | None = None,
    user_projects: list[dict] | None = None,
    global_username: str | None = None,
    global_email: str | None = None,
) -> tuple[dict[str, int], dict[str, set[int]], dict[str, dict[int, list[EventDetail]]]]:
    logger.debug(
        f"[GitLab] Fetching commits for user_id={user_id}, gitlab_username={gitlab_username}, {start_date} to {end_date}"
    )
    counts: dict[str, int] = defaultdict(int)
    active_hours: dict[str, set[int]] = defaultdict(set)
    events: dict[str, dict[int, list[EventDetail]]] = defaultdict(lambda: defaultdict(list))

    user_obj = users.get_user_by_username(gl_client, gitlab_username)
    if not user_obj:
        logger.debug(f"[GitLab] Could not find user object for {gitlab_username}")
        return dict(counts), dict(active_hours), dict(events)

    if override_email:
        user_obj["override_email"] = override_email
    if override_username:
        user_obj["override_username"] = override_username
    if global_username:
        user_obj["global_username"] = global_username
    if global_email:
        user_obj["global_email"] = global_email

    # Reuse pre-fetched projects if provided to avoid a duplicate API call
    if user_projects is not None:
        all_projs = user_projects
    else:
        fetched = gitlab_projects.get_user_projects(gl_client, user_id, gitlab_username)
        all_projs = fetched.get("all", [])
    if not all_projs:
        logger.debug(f"[GitLab] No projects found for user {gitlab_username}")
        return dict(counts), dict(active_hours), dict(events)

    logger.debug(f"[GitLab] Fetching commits across {len(all_projs)} projects")
    api_since = (start_date - timedelta(days=1)).isoformat()
    api_until = (end_date + timedelta(days=1)).isoformat()
    all_commits, _, _ = commits.get_user_commits(gl_client, user_obj, all_projs, since=api_since, until=api_until)
    start_date_str = start_date.isoformat()
    end_date_str = end_date.isoformat()

    for commit in all_commits or []:
        commit_date = commit.get("date", "")
        if commit_date and commit_date != "N/A" and start_date_str <= commit_date <= end_date_str:
            counts[commit_date] += 1
            # Extract hour from the commit's 'time' field which is "HH:MM:SS"
            time_str = commit.get("time", "")
            if time_str and ":" in time_str:
                try:
                    hour = int(time_str.split(":")[0])
                    active_hours[commit_date].add(hour)
                    c_title = commit.get("message", "Commit").split("\n")[0]
                    events[commit_date][hour].append(
                        {
                            "type": "commit",
                            "title": c_title,
                            "url": commit.get("web_url", ""),
                            "timestamp": commit.get("created_at") or commit.get("date"),
                        }
                    )
                except Exception:
                    pass

    logger.debug(f"[GitLab] Commits by date: {dict(counts)}")
    return dict(counts), dict(active_hours), dict(events)


def aggregate_intern_data(
    gl_client,
    gitlab_username: str,
    corpus_uid: str,
    intern_name: str,
    start_date: date,
    end_date: date,
    override_email: str | None = None,
    override_username: str | None = None,
    global_username: str | None = None,
    global_email: str | None = None,
) -> WeeklyActivity:
    """Aggregate all GitLab activity for one intern into WeeklyActivity model."""
    logger.debug(
        f"[Aggregator] aggregate_intern_data for {intern_name} ({gitlab_username}) from {start_date} to {end_date}"
    )
    user_id = _get_user_id(gl_client, gitlab_username)
    if not user_id:
        logger.warning(f"[Aggregator] Could not find GitLab user_id for {gitlab_username}")
        return WeeklyActivity(intern_name=intern_name, gitlab_username=gitlab_username, corpus_uid=corpus_uid)

    from internship_activity_tracker.infrastructure.gitlab.timelogs import (
        aggregate_daily_time_categorized,
        build_daily_time_from_time_stats,
        fetch_user_timelogs_from_projects,
    )

    # Fetch user projects once — reused for timelogs AND commits
    user_projects = gitlab_projects.get_user_projects(gl_client, user_id, gitlab_username)
    all_projs = user_projects.get("all", [])
    logger.info(f"[Aggregator] Found {len(all_projs)} projects for {gitlab_username}")

    # ── Fetch issues and MRs first (needed for time_stats fallback) ──
    mr_counts, mr_hours, mr_events, raw_mrs = _fetch_mrs_by_date(gl_client, user_id, start_date, end_date)
    issue_counts, issue_hours, issue_events, raw_issues = _fetch_issues_by_date(
        gl_client, user_id, start_date, end_date
    )
    # Discover projects from issues/MRs that might have been missed by get_user_projects
    activity_project_ids = set()
    for mr in raw_mrs:
        pid = mr.get("project_id")
        if pid:
            activity_project_ids.add(pid)
    for issue in raw_issues:
        pid = issue.get("project_id")
        if pid:
            activity_project_ids.add(pid)

    existing_project_ids = {p["id"] for p in all_projs}
    missing_project_ids = activity_project_ids - existing_project_ids

    if missing_project_ids:
        logger.info(
            f"[Aggregator] Discovered {len(missing_project_ids)} extra projects from MRs/Issues for {gitlab_username}"
        )
        for pid in missing_project_ids:
            all_projs.append({"id": pid})

    # ── Strategy 1: timelogs endpoint (global + per-project) ──
    logger.info(f"[Aggregator] Fetching timelogs for {gitlab_username} across {len(all_projs)} projects")
    timelogs = fetch_user_timelogs_from_projects(gl_client, user_id, all_projs, start_date, end_date)
    logger.info(f"[Aggregator] Timelogs fetched: {len(timelogs)}")
    daily_times, daily_categorized, seen_iss, seen_mrs, activity_timestamps = aggregate_daily_time_categorized(
        timelogs, raw_issues, raw_mrs
    )

    # ── Strategy 2: Supplement with time_stats fallback ──
    logger.info(f"[Aggregator] Supplementing daily_times with issue/MR time_stats for {gitlab_username}")
    daily_times, daily_categorized = build_daily_time_from_time_stats(
        raw_issues,
        raw_mrs,
        gl_client,
        start_date.isoformat(),
        end_date.isoformat(),
        existing_daily_times=daily_times,
        existing_categorized=daily_categorized,
        issue_formal_totals=seen_iss,
        mr_formal_totals=seen_mrs,
    )
    logger.info(f"[Aggregator] Final daily_times after supplementation: {daily_times}")

    commit_counts, commit_hours, commit_events = _fetch_commits_by_date(
        gl_client,
        user_id,
        gitlab_username,
        start_date,
        end_date,
        override_email=override_email,
        override_username=override_username,
        user_projects=all_projs,
        global_username=global_username,
        global_email=global_email,
    )

    all_dates: set[str] = set()
    all_dates.update(daily_times.keys())
    all_dates.update(mr_counts.keys())
    all_dates.update(issue_counts.keys())
    all_dates.update(commit_counts.keys())
    logger.debug(f"[Aggregator] All dates with activity: {all_dates}")

    daily_data: dict[str, DailyData] = {}
    total_weekly_time = 0

    for date_str in sorted(all_dates):
        # Combine hours from all sources
        combined_hours: set[int] = set()
        combined_hours.update(mr_hours.get(date_str, []))
        combined_hours.update(issue_hours.get(date_str, []))
        combined_hours.update(commit_hours.get(date_str, []))

        combined_events: dict[int, list[EventDetail]] = defaultdict(list)
        for hr in mr_events.get(date_str, {}):
            combined_events[hr].extend(mr_events[date_str][hr])
        for hr in issue_events.get(date_str, {}):
            combined_events[hr].extend(issue_events[date_str][hr])
        for hr in commit_events.get(date_str, {}):
            combined_events[hr].extend(commit_events[date_str][hr])

        cats = daily_categorized.get(date_str, {})
        # Filter timestamps for this specific date
        day_timestamps = [ts for ts in activity_timestamps if ts.startswith(date_str)]

        gitlab: GitLabDailyData = {
            "mrs": mr_counts.get(date_str, 0),
            "issues": issue_counts.get(date_str, 0),
            "commits": commit_counts.get(date_str, 0),
            "time_spent_seconds": daily_times.get(date_str, 0),
            "mrs_open_time": cats.get("mrs_open", 0),
            "mrs_merged_time": cats.get("mrs_merged", 0),
            "issues_open_time": cats.get("issues_open", 0),
            "issues_closed_time": cats.get("issues_closed", 0),
            "active_hours": sorted(combined_hours),
            "activity_timestamps": day_timestamps,
            "events_by_hour": dict(combined_events),
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
            corpus_uid=row.get("corpus_username", ""),
            intern_name=row.get("name", ""),
            start_date=start_date,
            end_date=end_date,
            global_username=row.get("global_username"),
            global_email=row.get("global_email"),
        )
        results.append(activity)
    return results
