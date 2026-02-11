import tomllib


def parse_uvlock_content(content: str):
    """
    Parse uv.lock TOML content and return dependency info.
    """
    try:
        data = tomllib.loads(content)
    except Exception:
        return {"error": "Invalid uv.lock format"}

    packages = []

    for package in data.get("package", []):
        packages.append(
            {
                "name": package.get("name"),
                "version": package.get("version"),
                "source": package.get("source", {}).get("type"),
            }
        )

    return {
        "total_dependencies": len(packages),
        "packages": packages,
    }


def extract_dependencies_from_project(project, branch="main"):
    """
    Fetch uv.lock from GitLab project and parse it.
    """
    try:
        file = project.files.get(file_path="uv.lock", ref=branch)
        content = file.decode().decode("utf-8")
        return parse_uvlock_content(content)
    except Exception:
        return {"error": "uv.lock not found or unreadable"}
