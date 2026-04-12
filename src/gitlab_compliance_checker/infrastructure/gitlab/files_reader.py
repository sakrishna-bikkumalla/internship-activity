import base64
from typing import List, Optional
from urllib.parse import quote


def read_file_content(gl, project_id: int, file_path: str, ref: str) -> Optional[str]:
    """
    Safely read file content from a GitLab project using REST API.
    Returns file content or None.
    """
    try:
        encoded_path = quote(file_path, safe="")
        endpoint = f"/projects/{project_id}/repository/files/{encoded_path}"
        file_obj = gl._get(endpoint, params={"ref": ref})
        
        if file_obj and isinstance(file_obj, dict) and "content" in file_obj:
            content_bytes = base64.b64decode(file_obj["content"])
            return content_bytes.decode("utf-8")
        return None
    except Exception:
        return None


def list_all_files(gl, project_id: int, branch: str = "main") -> List[str]:
    """
    Return all file paths in repository recursively using REST API.
    """
    try:
        items = gl._get_paginated(
            f"/projects/{project_id}/repository/tree",
            params={"ref": branch, "recursive": True},
            per_page=100,
            max_pages=50,
        )

        return [item.get("path") for item in (items or []) if isinstance(item, dict) and item.get("type") == "blob"]
    except Exception:
        return []
