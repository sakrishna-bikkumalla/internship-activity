def classify_files(gl, project_id: int) -> dict:
    """
    Classifies files by type.
    """

    try:
        project = gl.projects.get(project_id)
        files = project.repository_tree(path="", recursive=True)

        counts: dict[str, int] = {}

        for f in files:
            name = f["name"]
            if "." in name:
                ext = name.split(".")[-1]
                counts[ext] = counts.get(ext, 0) + 1

        return counts

    except Exception as e:
        return {"error": str(e)}
