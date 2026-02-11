from datetime import datetime, timezone
from zoneinfo import ZoneInfo

# Set local timezone (IST)
LOCAL_TZ = ZoneInfo("Asia/Kolkata")


# ---------------- DATETIME HELPERS ----------------


def parse_gitlab_datetime(timestamp: str):
    """
    Convert GitLab UTC timestamp to local timezone (IST).
    Returns timezone-aware datetime or None.
    """
    if not timestamp:
        return None

    try:
        normalized = timestamp.replace("Z", "+00:00")
        dt = datetime.fromisoformat(normalized)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt.astimezone(LOCAL_TZ)

    except Exception:
        return None


def classify_time_slot(timestamp: str):
    """
    Classify time into:
    Morning   : 00:00 – 11:59
    Afternoon : 12:00 – 16:59
    Evening   : 17:00 – 23:59
    """
    dt = parse_gitlab_datetime(timestamp)
    if not dt:
        return None

    hour = dt.hour

    if 0 <= hour < 12:
        return "Morning"
    elif 12 <= hour < 17:
        return "Afternoon"
    else:
        return "Evening"


def format_date_time(timestamp: str):
    """
    Return formatted (date, time) in IST.
    """
    dt = parse_gitlab_datetime(timestamp)
    if not dt:
        return "-", "-"

    return dt.date().isoformat(), dt.strftime("%I:%M %p")


# ---------------- DATA PROCESSING ----------------


def process_commits(commits: list):
    """
    Process commit list into structured rows.
    """
    processed = []

    for commit in commits or []:
        created_at = commit.get("created_at") or commit.get("committed_date")

        slot = classify_time_slot(created_at)
        if slot is None:
            continue

        date_str, time_str = format_date_time(created_at)

        message = commit.get("title") or commit.get("message") or ""
        message = message.split("\n")[0]

        processed.append(
            {
                "project_type": commit.get("project_scope", "-"),
                "project": commit.get("project_name", "-"),
                "message": message,
                "date": date_str,
                "time": time_str,
                "slot": slot,
            }
        )

    return processed


def process_groups(groups: list):
    """
    Process group list into structured rows.
    """
    rows = []

    for group in groups or []:
        rows.append(
            {
                "name": group.get("name", "-"),
                "path": group.get("full_path") or group.get("path", "-"),
                "visibility": group.get("visibility", "-"),
                "web_url": group.get("web_url", "-"),
            }
        )

    return rows
