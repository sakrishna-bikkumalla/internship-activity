"""
Timelog fetching strategies for GitLab Weekly Performance Tracker.

Strategy order (most reliable first):
  1. Global  GET /timelogs?user_id=...  — catches all projects
  2. Per-project GET /projects/:id/timelogs — supplements in case global is restricted
  3. Issue/MR time_stats fallback — used when timelog endpoints return nothing
"""

import asyncio
import logging
from collections import defaultdict
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def fetch_user_timelogs(
    gl_client,
    username: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch timelogs for a user via the global endpoint (kept for compatibility)."""
    u_data = gl_client._get("/users", params={"username": username})
    target_user = next(
        (u for u in (u_data or []) if str(u.get("username", "")).lower() == str(username).lower()),
        None,
    )
    if not target_user:
        return []

    user_id = target_user["id"]
    params = {
        "user_id": user_id,
        "start_date": start_date.isoformat() if isinstance(start_date, date) else start_date,
        "end_date": end_date.isoformat() if isinstance(end_date, date) else end_date,
    }
    try:
        timelogs = gl_client._get("/timelogs", params=params)
        return timelogs if isinstance(timelogs, list) else []
    except Exception as exc:
        logger.warning(f"[Timelogs] Global /timelogs failed: {exc}")
        return []


def fetch_user_timelogs_from_projects(
    gl_client,
    user_id: int,
    projects: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch timelogs using multiple strategies and deduplicate.

    Strategy 1 — Global endpoint (catches ALL projects, even issue-only ones):
        GET /timelogs?user_id=...&start_date=...&end_date=...

    Strategy 2 — Per-project endpoint (supplements if global is restricted):
        GET /projects/:id/timelogs?user_id=...&start_date=...&end_date=...

    Returns:
        Combined, deduplicated list of timelog dicts.
    """
    seen_ids: set[int] = set()
    all_timelogs: list[dict[str, Any]] = []

    params = {
        "user_id": user_id,
        "start_date": start_date.isoformat() if isinstance(start_date, date) else str(start_date),
        "end_date": end_date.isoformat() if isinstance(end_date, date) else str(end_date),
    }

    def _add_logs(logs: Any) -> int:
        count = 0
        for log in logs or []:
            if not isinstance(log, dict):
                continue
            log_id = log.get("id")
            if log_id and log_id in seen_ids:
                continue
            if log_id:
                seen_ids.add(log_id)
            all_timelogs.append(log)
            count += 1
        return count

    # Strategy 1: global /timelogs
    try:
        global_logs = gl_client._get("/timelogs", params=params)
        count = _add_logs(global_logs)
        logger.info(f"[Timelogs] Global /timelogs → {count} logs for user_id={user_id}")
    except Exception as exc:
        logger.warning(f"[Timelogs] Global /timelogs failed ({type(exc).__name__}: {exc}) — will try per-project")

    # Strategy 2: per-project /timelogs
    for project in projects:
        project_id = project.get("id")
        if not project_id:
            continue
        try:
            proj_logs = gl_client._get(f"/projects/{project_id}/timelogs", params=params)
            added = _add_logs(proj_logs)
            if added:
                logger.info(f"[Timelogs] Project {project_id} added {added} new logs")
        except Exception as exc:
            logger.debug(f"[Timelogs] Skipping project {project_id}: {exc}")

    logger.info(f"[Timelogs] Total unique timelogs: {len(all_timelogs)}")
    return all_timelogs


async def fetch_user_timelogs_from_projects_async(
    gl_client,
    user_id: int,
    projects: list[dict[str, Any]],
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Async version of fetch_user_timelogs_from_projects."""
    seen_ids: set[int] = set()
    all_timelogs: list[dict[str, Any]] = []

    params = {
        "user_id": user_id,
        "start_date": start_date.isoformat() if isinstance(start_date, date) else str(start_date),
        "end_date": end_date.isoformat() if isinstance(end_date, date) else str(end_date),
    }

    def _add_logs(logs: Any) -> int:
        count = 0
        for log in logs or []:
            if not isinstance(log, dict):
                continue
            log_id = log.get("id")
            if log_id and log_id in seen_ids:
                continue
            if log_id:
                seen_ids.add(log_id)
            all_timelogs.append(log)
            count += 1
        return count

    # Strategy 1: global /timelogs
    try:
        global_logs = await gl_client._async_get("/timelogs", params=params)
        count = _add_logs(global_logs)
        logger.info(f"[Timelogs/Async] Global /timelogs → {count} logs for user_id={user_id}")
    except Exception as exc:
        logger.warning(f"[Timelogs/Async] Global /timelogs failed ({type(exc).__name__}: {exc})")

    # Strategy 2: per-project /timelogs (Concurrent)
    async def _fetch_one(pid):
        try:
            return await gl_client._async_get(f"/projects/{pid}/timelogs", params=params)
        except Exception:
            return []

    p_ids = [p.get("id") for p in projects if p.get("id")]
    if p_ids:
        tasks = [_fetch_one(pid) for pid in p_ids]
        results = await asyncio.gather(*tasks)
        for proj_logs in results:
            _add_logs(proj_logs)

    logger.info(f"[Timelogs/Async] Total unique timelogs: {len(all_timelogs)}")
    return all_timelogs


def format_time_spent(seconds: int) -> str:
    """Format seconds into 'X hr Y min'."""
    if not seconds:
        return "0 min"
    hours = seconds // 3600
    minutes = (seconds % 3600) // 60
    if hours > 0:
        return f"{hours} hr {minutes} min"
    return f"{minutes} min"


def build_daily_time_from_time_stats(
    issues: list[dict[str, Any]],
    mrs: list[dict[str, Any]],
    gl_client: Any,
    start_date_str: str,
    end_date_str: str,
    existing_daily_times: dict[str, int] | None = None,
    existing_categorized: dict[str, dict[str, int]] | None = None,
    issue_formal_totals: dict[int, int] | None = None,
    mr_formal_totals: dict[int, int] | None = None,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    """Fallback/Supplement: derive daily time from issue/MR time_stats.

    Returns:
        (Updated total_daily, Updated categorized_daily)
    """
    daily_totals: dict[str, int] = defaultdict(int)
    categorized: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    if existing_daily_times:
        daily_totals.update(existing_daily_times)
    if existing_categorized:
        for d, cats in existing_categorized.items():
            categorized[d].update(cats)

    f_issues = issue_formal_totals or {}
    f_mrs = mr_formal_totals or {}

    for issue in issues:
        pid = issue.get("project_id")
        iid = issue.get("iid")
        gid = issue.get("id")
        act_timestamp = issue.get("closed_at") or issue.get("created_at", "")
        date_str = str(act_timestamp)[:10]

        # Basic range check
        if not (pid and iid and start_date_str <= date_str <= end_date_str):
            continue

        ts = issue.get("time_stats") or {}
        if not ts:
            try:
                ts = gl_client._get(f"/projects/{pid}/issues/{iid}/time_stats") or {}
            except Exception:
                ts = {}

        total_ts = ts.get("total_time_spent", 0)
        formal_ts = f_issues.get(gid, 0) if gid else 0

        if total_ts > formal_ts:
            extra = int(total_ts - formal_ts)
            daily_totals[date_str] += extra
            cat = "issues_closed" if issue.get("state") == "closed" else "issues_open"
            categorized[date_str][cat] += extra
            logger.info(
                f"[Timelogs/time_stats] Supplemented Issue #{iid} with {extra}s extra (Total: {total_ts}s) on {date_str}"
            )

    for mr in mrs:
        pid = mr.get("project_id")
        iid = mr.get("iid")
        gid = mr.get("id")
        act_timestamp = mr.get("merged_at") or mr.get("closed_at") or mr.get("updated_at", "")
        date_str = str(act_timestamp)[:10]

        # Basic range check
        if not (pid and iid and start_date_str <= date_str <= end_date_str):
            continue

        ts = mr.get("time_stats") or {}
        if not ts:
            try:
                ts = gl_client._get(f"/projects/{pid}/merge_requests/{iid}/time_stats") or {}
            except Exception:
                ts = {}

        total_ts = ts.get("total_time_spent", 0)
        formal_ts = f_mrs.get(gid, 0) if gid else 0

        if total_ts > formal_ts:
            extra = int(total_ts - formal_ts)
            daily_totals[date_str] += extra
            cat = "mrs_merged" if mr.get("state") == "merged" else "mrs_open"
            categorized[date_str][cat] += extra
            logger.info(
                f"[Timelogs/time_stats] Supplemented MR !{iid} with {extra}s extra (Total: {total_ts}s) on {date_str}"
            )

    return dict(daily_totals), {d: dict(c) for d, c in categorized.items()}


def aggregate_daily_time_categorized(
    timelogs: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    mrs: list[dict[str, Any]],
) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[int, int], dict[int, int], list[str]]:
    """Aggregate timelogs into daily totals and categories.

    Returns:
        (total_daily, categorized_daily, issue_formal_totals, mr_formal_totals, activity_timestamps)
    """
    daily_totals: dict[str, int] = defaultdict(int)
    categorized: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    issue_formal_totals: dict[int, int] = defaultdict(int)
    mr_formal_totals: dict[int, int] = defaultdict(int)
    activity_timestamps: list[str] = []

    # Build lookup for state by ID or IID
    # Since timelogs from global endpoint might only have global IDs, we'll try to match both
    issue_states = {}  # issue_id -> state
    mr_states = {}  # mr_id -> state
    issue_iid_states = {}  # (project_id, iid) -> state
    mr_iid_states = {}  # (project_id, iid) -> state

    for iss in issues:
        state = iss.get("state", "opened")
        issue_states[iss.get("id")] = state
        pid = iss.get("project_id")
        iid = iss.get("iid")
        if pid and iid:
            issue_iid_states[(pid, iid)] = state

    for mr in mrs:
        state = mr.get("state", "opened")
        mr_states[mr.get("id")] = state
        pid = mr.get("project_id")
        iid = mr.get("iid")
        if pid and iid:
            mr_iid_states[(pid, iid)] = state

    for log in timelogs:
        spent_at = log.get("spent_at") or log.get("date", "")
        if not spent_at:
            continue

        # Keep track of the full timestamp for exact activity tracking
        activity_timestamps.append(str(spent_at))

        log_date = str(spent_at)[:10]

        time_spent = log.get("time_spent", 0)
        if not isinstance(time_spent, (int, float)):
            continue
        spent_int = int(time_spent)
        daily_totals[log_date] += spent_int

        # Determine Category
        cat = "other"

        # GitLab sometimes nests these or uses different keys
        iss_id = log.get("issue_id") or (log.get("issue") or {}).get("id")
        mr_id = log.get("merge_request_id") or (log.get("merge_request") or {}).get("id")
        iss_iid = log.get("issue_iid") or (log.get("issue") or {}).get("iid")
        mr_iid = log.get("merge_request_iid") or (log.get("merge_request") or {}).get("iid")
        pid = (
            log.get("project_id")
            or (log.get("issue") or {}).get("project_id")
            or (log.get("merge_request") or {}).get("project_id")
        )

        if mr_id and mr_id in mr_states:
            cat = "mrs_merged" if mr_states[mr_id] == "merged" else "mrs_open"
            mr_formal_totals[mr_id] += spent_int
        elif iss_id and iss_id in issue_states:
            cat = "issues_closed" if issue_states[iss_id] == "closed" else "issues_open"
            issue_formal_totals[iss_id] += spent_int
        elif pid and mr_iid and (pid, mr_iid) in mr_iid_states:
            cat = "mrs_merged" if mr_iid_states[(pid, mr_iid)] == "merged" else "mrs_open"
        elif pid and iss_iid and (pid, iss_iid) in issue_iid_states:
            cat = "issues_closed" if issue_iid_states[(pid, iss_iid)] == "closed" else "issues_open"
        else:
            # Fallback if we can't find the item in our fetched lists
            if mr_iid or mr_id:
                cat = "mrs_open"  # Default to open if state unknown
            elif iss_iid or iss_id:
                cat = "issues_open"

        categorized[log_date][cat] += spent_int

    return (
        dict(daily_totals),
        {d: dict(c) for d, c in categorized.items()},
        dict(issue_formal_totals),
        dict(mr_formal_totals),
        sorted(set(activity_timestamps)),
    )


def aggregate_daily_time(
    timelogs: list[dict[str, Any]],
) -> dict[str, int]:
    """Backward compatible wrapper for aggregate_daily_time_categorized."""
    totals, _, _, _, _ = aggregate_daily_time_categorized(timelogs, [], [])
    return totals
