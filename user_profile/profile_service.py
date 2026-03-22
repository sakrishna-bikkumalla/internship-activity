from datetime import datetime, time
from urllib.parse import urlparse


# ---------------- HELPERS ----------------


def _extract_username_from_input(username_or_id):
    value = str(username_or_id or "").strip()
    if not value:
        return ""
    if value.startswith(("http://", "https://")):
        path = urlparse(value).path.strip("/")
        if path:
            return path.split("/")[0]
    return value


def _safe_getattr_dict_id(obj, attr_name):
    value = getattr(obj, attr_name, None)
    if isinstance(value, dict):
        return value.get("id")
    return None


def _get_issue_assignee_ids(issue):
    ids = set()

    if isinstance(getattr(issue, "assignee", None), dict):
        ids.add(issue.assignee.get("id"))

    if isinstance(getattr(issue, "assignees", None), list):
        for item in issue.assignees:
            if isinstance(item, dict) and item.get("id") is not None:
                ids.add(item["id"])

    return {i for i in ids if i is not None}


def _issue_is_related_to_user(issue, user_id):
    author_id = _safe_getattr_dict_id(issue, "author")
    return author_id == user_id or user_id in _get_issue_assignee_ids(issue)


# ---------------- ISSUE FETCHING ----------------


def _fetch_user_related_issues_by_state(gl, user_id, state=None, limit=200):
    all_issues = {}

    params = {
        "scope": "all",
        "order_by": "created_at",
        "sort": "desc",
        "per_page": 100,
    }

    if state and state != "all":
        params["state"] = state

    # Try ID-based filters
    for key in ("author_id", "assignee_id"):
        try:
            issues = gl.issues.list(**params, **{key: user_id})
            for issue in issues:
                all_issues[issue.id] = issue
        except Exception:
            pass

    # Fallback to username-based filters
    if not all_issues:
        try:
            user = gl.users.get(user_id)
            username = user.username
            for key in ("author_username", "assignee_username"):
                try:
                    issues = gl.issues.list(**params, **{key: username})
                    for issue in issues:
                        all_issues[issue.id] = issue
                except Exception:
                    pass
        except Exception:
            pass

    issues = list(all_issues.values())
    issues.sort(key=lambda i: getattr(i, "created_at", "") or "", reverse=True)

    return issues[:limit]


def _get_total_count_from_api(gl, endpoint, query_data=None):
    try:
        response = gl.http_get(
            endpoint,
            query_data={"per_page": 1, "page": 1, **(query_data or {})},
            raw=True,
        )
        total = response.headers.get("X-Total")
        return int(total) if total else None
    except Exception:
        return None


# ---------------- USER PROFILE ----------------


def get_user_profile(client, username_or_id):
    try:
        cleaned = _extract_username_from_input(username_or_id)

        if cleaned.isdigit():
            return client.users.get(int(cleaned))

        users = client.users.list(username=cleaned)
        return users[0] if users else None
    except Exception:
        return None


# ---------------- USER COUNTS ----------------


def get_user_projects_count(gl, user_id):
    total = _get_total_count_from_api(gl, f"/users/{user_id}/projects")
    if total is not None:
        return total
    try:
        return len(gl.users.get(user_id).projects.list(all=True))
    except Exception:
        return 0


def get_user_groups_count(gl, user_id):
    total = _get_total_count_from_api(gl, f"/users/{user_id}/groups")
    if total is not None:
        return total
    try:
        return len(gl.users.get(user_id).groups.list(all=True))
    except Exception:
        return 0


def get_user_open_mrs_count(gl, user_id):
    total = _get_total_count_from_api(
        gl,
        "/merge_requests",
        query_data={"author_id": user_id, "state": "opened", "scope": "all"},
    )
    if total is not None:
        return total

    try:
        return len(gl.mergerequests.list(author_id=user_id, state="opened", all=True))
    except Exception:
        return 0


def get_user_open_issues_count(gl, user_id):
    try:
        issues = _fetch_user_related_issues_by_state(gl, user_id, state="opened")
        return len(issues)
    except Exception:
        return 0


# ---------------- ISSUE DETAILS ----------------


def get_user_issues_details(gl, user_id):
    issues = _fetch_user_related_issues_by_state(gl, user_id, state="all")

    today = datetime.now().date()
    morning_end = time(12, 0, 0)

    stats = {
        "total": len(issues),
        "open": 0,
        "closed": 0,
        "today_morning": 0,
        "today_afternoon": 0,
    }

    for issue in issues:
        state = getattr(issue, "state", "")
        if state == "opened":
            stats["open"] += 1
        elif state == "closed":
            stats["closed"] += 1

        created_at = getattr(issue, "created_at", "")
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            if created.date() == today:
                if created.time() <= morning_end:
                    stats["today_morning"] += 1
                else:
                    stats["today_afternoon"] += 1
        except Exception:
            pass

    return stats


# ---------------- ISSUE LIST FOR UI ----------------


def get_user_issues_list(gl, user_id, limit=100):
    issues = _fetch_user_related_issues_by_state(gl, user_id, state="all")

    rows = []
    for issue in issues[:limit]:
        assignees = []
        if isinstance(getattr(issue, "assignees", None), list):
            assignees = [
                a.get("username") for a in issue.assignees if isinstance(a, dict)
            ]

        rows.append(
            {
                "id": issue.id,
                "iid": issue.iid,
                "title": issue.title,
                "state": issue.state,
                "project_id": issue.project_id,
                "created_at": issue.created_at,
                "updated_at": issue.updated_at,
                "web_url": issue.web_url,
                "assignees": ", ".join([a for a in assignees if a]),
            }
        )

    return rows


# ---------------- PROFILE README CHECK ----------------


def check_profile_readme(gl, username):
    try:
        project_path = f"{username}/{username}"
        project = gl.projects.get(project_path)

        project.files.get(
            file_path="README.md",
            ref=project.default_branch or "main",
        )

        return {
            "exists": True,
            "url": f"{project.web_url}/-/blob/{project.default_branch or 'main'}/README.md",
        }

    except Exception:
        return {"exists": False}
