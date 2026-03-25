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
    Morning:   09:00 – 12:30
    Afternoon: 14:00 – 17:00
    Other:     All other times
    """
    dt = parse_gitlab_datetime(timestamp)
    if not dt:
        return None

    hour = dt.hour
    minute = dt.minute

    # Morning: 9:00 AM to 12:30 PM
    # 9, 10, 11 are fully in. 12 is in if minute <= 30.
    if (9 <= hour < 12) or (hour == 12 and minute <= 30):
        return "Morning"

    # Afternoon: 2:00 PM to 5:00 PM (14:00 - 17:00)
    # 14, 15, 16 are fully in. 17:00 is exactly on the edge, usually "until 5" includes 5:00 or excludes?
    # User said "2-5 pm". I'll assume 14:00:00 to 17:00:00 inclusive.
    if 14 <= hour <= 17:
        if hour == 17 and minute > 0:
            return "Other"
        return "Afternoon"

    return "Other"


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
