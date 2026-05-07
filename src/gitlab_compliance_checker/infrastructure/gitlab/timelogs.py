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
) -> dict[str, int]:
    """Fallback/Supplement: derive daily time from issue/MR time_stats.

    Args:
        issues: List of issue dicts already fetched
        mrs: List of MR dicts already fetched
        gl_client: GitLabClient for supplementary time_stats calls
        start_date_str: YYYY-MM-DD inclusive start
        end_date_str: YYYY-MM-DD inclusive end
        existing_daily_times: Existing daily totals (seconds) to supplement.

    Returns:
        Updated dict mapping "YYYY-MM-DD" -> total seconds
    """
    daily_totals: dict[str, int] = defaultdict(int)
    if existing_daily_times:
        daily_totals.update(existing_daily_times)

    # We use a heuristic: if we already have substantial time for a day,
    # we assume timelogs worked. If we have 0 or very little time, and
    # an issue says it has time, we add it.

    for issue in issues:
        pid = issue.get("project_id")
        iid = issue.get("iid")
        date_str = str(issue.get("created_at", ""))[:10]
        if not (pid and iid and start_date_str <= date_str <= end_date_str):
            continue

        # If we already have time for this day, skip to avoid double counting
        # unless the existing time is 0.
        if daily_totals.get(date_str, 0) > 0 and existing_daily_times:
            continue

        ts = issue.get("time_stats") or {}
        if not ts:
            try:
                ts = gl_client._get(f"/projects/{pid}/issues/{iid}/time_stats") or {}
            except Exception:
                ts = {}
        spent = ts.get("total_time_spent", 0)
        if isinstance(spent, (int, float)) and spent > 0:
            daily_totals[date_str] += int(spent)
            logger.info(f"[Timelogs/time_stats] Supplemented Issue #{iid} on {date_str}: {spent}s")

    for mr in mrs:
        pid = mr.get("project_id")
        iid = mr.get("iid")
        date_str = str(mr.get("merged_at") or mr.get("updated_at") or "")[:10]
        if not (pid and iid and start_date_str <= date_str <= end_date_str):
            continue

        if daily_totals.get(date_str, 0) > 0 and existing_daily_times:
            continue

        ts = mr.get("time_stats") or {}
        if not ts:
            try:
                ts = gl_client._get(f"/projects/{pid}/merge_requests/{iid}/time_stats") or {}
            except Exception:
                ts = {}
        spent = ts.get("total_time_spent", 0)
        if isinstance(spent, (int, float)) and spent > 0:
            daily_totals[date_str] += int(spent)
            logger.info(f"[Timelogs/time_stats] Supplemented MR !{iid} on {date_str}: {spent}s")

    return dict(daily_totals)


def aggregate_daily_time(
    timelogs: list[dict[str, Any]],
) -> dict[str, int]:
    """Aggregate timelogs into daily totals.

    Handles both ``spent_at`` (project-level endpoint) and ``date``
    (global endpoint) field names.

    Returns:
        Dict mapping "YYYY-MM-DD" -> total seconds spent that day
    """
    daily_totals: dict[str, int] = defaultdict(int)

    for log in timelogs:
        log_date = log.get("spent_at") or log.get("date", "")
        if not log_date:
            continue
        log_date = str(log_date)[:10]

        time_spent = log.get("time_spent", 0)
        if isinstance(time_spent, (int, float)):
            daily_totals[log_date] += int(time_spent)

    return dict(daily_totals)
