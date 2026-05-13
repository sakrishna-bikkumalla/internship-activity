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
    assignee = issue.get("assignee")
    if isinstance(assignee, dict):
        ids.add(assignee.get("id"))
    assignees = issue.get("assignees")
    if isinstance(assignees, list):
        for item in assignees:
            if isinstance(item, dict) and item.get("id") is not None:
                ids.add(item.get("id"))
    return {i for i in ids if i is not None}


def _issue_is_related_to_user(issue, user_id):
    author = issue.get("author")
    author_id = author.get("id") if isinstance(author, dict) else None
    return author_id == user_id or user_id in _get_issue_assignee_ids(issue)


def _fetch_user_related_issues_by_state(gl_client, user_id, state=None, limit=200):
    all_issues = {}
    params = {"per_page": 100}
    if state and state != "all":
        params["state"] = state

    # author_id/assignee_id scope
    for key in ("author_id", "assignee_id"):
        try:
            issues = gl_client._get_paginated("/issues", params={**params, "scope": "all", key: user_id}, all=True)
            for issue in issues or []:
                all_issues[issue.get("id")] = issue
        except Exception:
            pass

    # Fallback to username if no issues found
    if not all_issues:
        try:
            user = gl_client._get(f"/users/{user_id}")
            username = user.get("username")
            if username:
                for key in ("author_username", "assignee_username"):
                    try:
                        issues = gl_client._get_paginated(
                            "/issues", params={**params, "scope": "all", key: username}, all=True
                        )
                        for issue in issues or []:
                            all_issues[issue.get("id")] = issue
                    except Exception:
                        pass
        except Exception:
            pass

    issues = list(all_issues.values())
    issues.sort(key=lambda i: i.get("created_at") or "", reverse=True)
    return issues[:limit]


def _get_total_count_from_api(gl_client, endpoint, query_data=None):
    try:
        items = gl_client._get_paginated(
            endpoint,
            params={**(query_data or {})},
            per_page=100,
            max_pages=50,
        )
        return len(items) if items is not None else None
    except Exception:
        return None


def get_user_profile(gl_client, username_or_id):
    try:
        cleaned = _extract_username_from_input(username_or_id)
        if cleaned.isdigit():
            return gl_client._get(f"/users/{cleaned}")
        users = gl_client._get("/users", params={"username": cleaned})
        return users[0] if isinstance(users, list) and users else None
    except Exception:
        return None


def get_user_projects_count(gl_client, user_id):
    total = _get_total_count_from_api(gl_client, f"/users/{user_id}/projects")
    return total if total is not None else 0


def get_user_groups_count(gl_client, user_id):
    total = _get_total_count_from_api(gl_client, f"/users/{user_id}/groups")
    return total if total is not None else 0


def get_user_open_mrs_count(gl_client, user_id):
    total = _get_total_count_from_api(
        gl_client, "/merge_requests", query_data={"author_id": user_id, "state": "opened", "scope": "all"}
    )
    return total if total is not None else 0


def get_user_open_issues_count(gl_client, user_id):
    try:
        issues = _fetch_user_related_issues_by_state(gl_client, user_id, state="opened")
        return len(issues)
    except Exception:
        return 0


# ---------------- ISSUE DETAILS ----------------


def get_user_issues_details(gl_client, user_id):
    issues = _fetch_user_related_issues_by_state(gl_client, user_id, state="all")
    today = datetime.now().date()
    morning_end = time(12, 0, 0)
    stats = {"total": len(issues), "open": 0, "closed": 0, "today_morning": 0, "today_afternoon": 0}

    for issue in issues:
        state = issue.get("state", "")
        if state == "opened":
            stats["open"] += 1
        elif state == "closed":
            stats["closed"] += 1

        created_at = issue.get("created_at", "")
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


def get_user_issues_list(gl_client, user_id, limit=100):
    issues = _fetch_user_related_issues_by_state(gl_client, user_id, state="all")
    rows = []
    for issue in issues[:limit]:
        assignees_raw = issue.get("assignees", [])
        assignees = (
            [a.get("username") for a in assignees_raw if isinstance(a, dict)] if isinstance(assignees_raw, list) else []
        )
        rows.append(
            {
                "id": issue.get("id"),
                "iid": issue.get("iid"),
                "title": issue.get("title"),
                "state": issue.get("state"),
                "project_id": issue.get("project_id"),
                "created_at": issue.get("created_at"),
                "updated_at": issue.get("updated_at"),
                "web_url": issue.get("web_url"),
                "assignees": ", ".join([a for a in assignees if a]),
            }
        )
    return rows


# ---------------- PROFILE README CHECK ----------------


def check_profile_readme(gl_client, username):
    try:
        project_path = str(f"{username}/{username}").replace("/", "%2F")
        project = gl_client._get(f"/projects/{project_path}")
        default_branch = project.get("default_branch") or "main"

        # Check file existence via generic GET
        # encoded path for README.md is README%2Emd
        gl_client._get(f"/projects/{project_path}/repository/files/README%2Emd", params={"ref": default_branch})

        return {
            "exists": True,
            "url": f"{project.get('web_url')}/-/blob/{default_branch}/README.md",
        }
    except Exception:
        return {"exists": False}
