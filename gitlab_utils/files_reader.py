# gitlab_utils/file_reader.py

from typing import List, Optional


def read_file_content(project, file_path: str, ref: str) -> Optional[str]:
    """
    Safely read file content from a GitLab project.
    Returns file content or None.
    """
    try:
        file_obj = project.files.get(file_path=file_path, ref=ref)
        return file_obj.decode().decode("utf-8")
    except Exception:
        return None


def list_all_files(project, branch: str = "main") -> List[str]:
    """
    Return all file paths in repository recursively.
    """
    try:
        try:
            items = project.repository_tree(
                ref=branch,
                recursive=True,
                all=True,
            )
        except TypeError:
            items = project.repository_tree(
                ref=branch,
                recursive=True,
            )

        return [item.get("path") for item in items if item.get("type") == "blob"]

    except Exception:
        return []
