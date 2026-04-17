from collections import defaultdict
from datetime import date
from typing import Any


def fetch_user_timelogs(
    gl_client,
    username: str,
    start_date: date,
    end_date: date,
) -> list[dict[str, Any]]:
    """Fetch all timelogs for a user within a date range.

    Args:
        gl_client: GitLabClient instance
        username: GitLab username
        start_date: Start date (inclusive)
        end_date: End date (inclusive)

    Returns:
        List of timelog dicts with fields like:
        {
            "id": int,
            "user_id": int,
            "date": "YYYY-MM-DD",
            "time_spent": int (seconds),
            "issue_id": int | None,
            "mr_id": int | None,
            ...
        }
    """
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

    timelogs = gl_client._get("/timelogs", params=params)
    return timelogs if timelogs else []


def aggregate_daily_time(
    timelogs: list[dict[str, Any]],
) -> dict[str, int]:
    """Aggregate timelogs into daily totals.

    Args:
        timelogs: List of timelog dicts from fetch_user_timelogs

    Returns:
        Dict mapping "YYYY-MM-DD" -> total seconds spent that day
    """
    daily_totals: dict[str, int] = defaultdict(int)

    for log in timelogs:
        log_date = log.get("date")
        if not log_date:
            continue

        time_spent = log.get("time_spent", 0)
        if isinstance(time_spent, (int, float)):
            daily_totals[str(log_date)] += int(time_spent)

    return dict(daily_totals)
