# gitlab_utils/api_helpers.py

from urllib.parse import urlparse

import requests


def extract_path_from_url(input_str):
    try:
        path = urlparse(input_str).path.strip("/")
        return path[:-4] if path.endswith(".git") else path
    except Exception:
        return str(input_str).strip()


def get_project_branches(project):
    try:
        branches = project.branches.list(all=True)
        return sorted([b.name for b in branches])
    except Exception:
        return []


def get_user_from_token(base_url, token):
    try:
        headers = {"PRIVATE-TOKEN": token}
        url = f"{base_url}/api/v4/user"
        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return f"Error validating token: {e}"


def get_user_groups_by_token(base_url, token):
    try:
        headers = {"PRIVATE-TOKEN": token}
        api_base = base_url.rstrip("/")

        if api_base.endswith("/api/v4"):
            url = f"{api_base}/groups?membership=true"
        else:
            url = f"{api_base}/api/v4/groups?membership=true"

        r = requests.get(url, headers=headers, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return f"Error fetching groups: {e}"
