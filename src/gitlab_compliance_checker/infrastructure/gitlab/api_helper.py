from urllib.parse import urlparse

import gitlab


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
        gl = gitlab.Gitlab(url=base_url, private_token=token, timeout=15, ssl_verify=False)
        gl.auth()
        if gl.user:
            return gl.user.as_dict()
        return "Error validating token: User is None"
    except Exception as e:
        return f"Error validating token: {e}"


def get_user_groups_by_token(base_url, token):
    try:
        gl = gitlab.Gitlab(url=base_url, private_token=token, timeout=15, ssl_verify=False)
        groups = gl.groups.list(membership=True, all=True)
        return [g.as_dict() for g in groups]
    except Exception as e:
        return f"Error fetching groups: {e}"
