from datetime import datetime, time
from urllib.parse import urlparse


def _extract_username_from_input(username_or_id):
    value = str(username_or_id or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
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

    assignee = getattr(issue, "assignee", None)
    if isinstance(assignee, dict) and assignee.get("id") is not None:
        ids.add(assignee["id"])

    assignees = getattr(issue, "assignees", None)
    if isinstance(assignees, list):
        for item in assignees:
            if isinstance(item, dict) and item.get("id") is not None:
                ids.add(item["id"])

    return ids


def _issue_is_related_to_user(issue, user_id):
    author_id = _safe_getattr_dict_id(issue, "author")
    return author_id == user_id or user_id in _get_issue_assignee_ids(issue)


def _fetch_all_user_issues(gl, user_id):
    """Fetch all user-related issues (open + closed) with safe fallbacks."""
    all_issues = {}

    try:
        for issue in gl.issues.list(author_id=user_id, all=True):
            all_issues[issue.id] = issue
    except Exception:
        pass

    try:
        for issue in gl.issues.list(assignee_id=user_id, all=True):
            all_issues[issue.id] = issue
    except Exception:
        pass

    # Final fallback for GitLab variants where above filters are limited
    if not all_issues:
        try:
            for issue in gl.issues.list(scope="all", all=True):
                if _issue_is_related_to_user(issue, user_id):
                    all_issues[issue.id] = issue
        except Exception:
            pass

    return list(all_issues.values())


def _fetch_user_related_issues_by_state(gl, user_id, state=None, limit=200):
    """Fetch user-related issues with bounded requests (prevents UI blanks/timeouts)."""
    all_issues = {}
    common_params = {
        "scope": "all",
        "order_by": "created_at",
        "sort": "desc",
        "per_page": 100,
        "page": 1,
    }
    if state:
        common_params["state"] = state

    # Try ID-based filters first
    for filter_key in ("author_id", "assignee_id"):
        try:
            issues = gl.issues.list(**common_params, **{filter_key: user_id})
            for issue in issues:
                all_issues[issue.id] = issue
        except Exception:
            pass

    # Fallback for GitLab variants: username-based filters
    if not all_issues:
        try:
            user = gl.users.get(user_id)
            username = getattr(user, "username", None)
            if username:
                for filter_key in ("author_username", "assignee_username"):
                    try:
                        issues = gl.issues.list(
                            **common_params, **{filter_key: username}
                        )
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
    """Read total count from GitLab pagination headers using a tiny request."""
    try:
        response = gl.http_get(
            endpoint,
            query_data={"per_page": 1, "page": 1, **(query_data or {})},
            raw=True,
        )
        total = response.headers.get("X-Total")
        return int(total) if total is not None else None
    except Exception:
        return None





def get_user_profile(client, username_or_id):
    try:
        cleaned = _extract_username_from_input(username_or_id)
        if str(cleaned).isdigit():
            return client.users.get(int(cleaned))
        users = client.users.list(username=cleaned)
        return users[0] if users else None
    except Exception:
        return None


# ---------------- USER COUNTS ----------------


def get_user_projects_count(gl, user_id):
    try:
        total = _get_total_count_from_api(gl, f"/users/{user_id}/projects")
        if total is not None:
            return total

        user = gl.users.get(user_id)
        return len(user.projects.list(all=True))
    except Exception:
        return 0


def get_user_groups_count(gl, user_id):
    try:
        total = _get_total_count_from_api(gl, f"/users/{user_id}/groups")
        if total is not None:
            return total

        user = gl.users.get(user_id)
        return len(user.groups.list(all=True))
    except Exception:
        return 0


def get_user_open_issues_count(gl, user_id):
    try:
        issues = _fetch_user_related_issues_by_state(gl, user_id, state="opened")
        return sum(1 for issue in issues if getattr(issue, "state", None) == "opened")
    except Exception:
        return 0


def get_user_open_mrs_count(gl, user_id):
    try:
        total = _get_total_count_from_api(
            gl,
            "/merge_requests",
            query_data={"author_id": user_id, "state": "opened", "scope": "all"},
        )
        if total is not None:
            return total

        mrs = gl.mergerequests.list(author_id=user_id, state="opened", all=True)
        return len(mrs)
    except Exception:
        return 0


# ---------------- ISSUE DETAILS ----------------


def get_user_issues_details(gl, user_id):
    try:
        issues = _fetch_user_related_issues_by_state(gl, user_id, state="all")

        total = len(issues)
        open_issues = 0
        closed_issues = 0
        today_morning = 0
        today_afternoon = 0

        today = datetime.now().date()
        morning_end = time(12, 0, 0)

        for issue in issues:
            if issue.state == "opened":
                open_issues += 1
            elif issue.state == "closed":
                closed_issues += 1

            created_at = getattr(issue, "created_at", None)
            if created_at:
                try:
                    created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                    if created.date() == today:
                        if created.time() <= morning_end:
                            today_morning += 1
                        else:
                            today_afternoon += 1
                except Exception:
                    pass

        return {
            "total": total,
            "open": open_issues,
            "closed": closed_issues,
            "today_morning": today_morning,
            "today_afternoon": today_afternoon,
        }

    except Exception:
        return {
            "total": 0,
            "open": 0,
            "closed": 0,
            "today_morning": 0,
            "today_afternoon": 0,
        }


def get_user_issues_list(gl, user_id, limit=100):
    """Return detailed user-related issues for UI display."""
    try:
        issues = _fetch_user_related_issues_by_state(gl, user_id, state="all")

        # Newest first
        def _sort_key(issue):
            return getattr(issue, "created_at", "") or ""

        issues = sorted(issues, key=_sort_key, reverse=True)

        rows = []
        for issue in issues[:limit]:
            assignees = []
            raw_assignees = getattr(issue, "assignees", None)
            if isinstance(raw_assignees, list):
                assignees = [
                    a.get("username") for a in raw_assignees if isinstance(a, dict)
                ]
            elif isinstance(getattr(issue, "assignee", None), dict):
                one = issue.assignee.get("username")
                if one:
                    assignees = [one]

            rows.append(
                {
                    "id": getattr(issue, "id", None),
                    "iid": getattr(issue, "iid", None),
                    "title": getattr(issue, "title", ""),
                    "state": getattr(issue, "state", ""),
                    "project_id": getattr(issue, "project_id", None),
                    "created_at": getattr(issue, "created_at", ""),
                    "updated_at": getattr(issue, "updated_at", ""),
                    "web_url": getattr(issue, "web_url", ""),
                    "assignees": ", ".join([a for a in assignees if a]),
                }
            )

        return rows
    except Exception:
        return []


# ---------------- PROFILE README CHECK ----------------


def check_profile_readme(gl, username):
    """
    Checks <username>/<username> project and README.md
    """
    try:
        projects = gl.projects.list(owned=True, all=True)

        for project in projects:
            if project.path.lower() == username.lower():
                try:
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

        return {"exists": False}

    except Exception as e:
        return {"exists": False, "error": str(e)}
