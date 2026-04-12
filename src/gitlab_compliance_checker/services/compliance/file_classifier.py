from typing import Optional


def classify_files(gl, project_id: int, ref: Optional[str] = None) -> dict:
    """
    Classifies files by type.
    """
    try:
        if not ref:
            project_info = gl._get(f"/projects/{project_id}")
            ref = project_info.get("default_branch", "main")

        files = gl._get_paginated(
            f"/projects/{project_id}/repository/tree",
            params={"ref": ref, "recursive": True},
            per_page=100,
            max_pages=50,
        )

        counts: dict[str, int] = {}

        for f in files or []:
            name = f.get("name", "")
            if "." in name:
                ext = name.split(".")[-1]
                counts[ext] = counts.get(ext, 0) + 1

        return counts
    except Exception as e:
        return {"error": str(e)}
