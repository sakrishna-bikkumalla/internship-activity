from typing import Optional


def classify_files(gl, project_id: int, ref: Optional[str] = None) -> dict:
    """
    Classifies files by type.
    """

    try:
        project = gl.projects.get(project_id)
        branch = ref or getattr(project, "default_branch", "main")
        files = project.repository_tree(path="", ref=branch, recursive=True, all=True)

        counts: dict[str, int] = {}

        for f in files:
            name = f["name"]
            if "." in name:
                ext = name.split(".")[-1]
                counts[ext] = counts.get(ext, 0) + 1

        return counts

    except Exception as e:
        return {"error": str(e)}
