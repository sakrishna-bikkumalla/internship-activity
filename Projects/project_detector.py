"""Project type detection based on root configuration files and deep inspection."""


def detect_project_type(filenames: list[str]) -> str:
    """
    Detect if a project is JavaScript/TypeScript or Python.

    Args:
        filenames: List of filenames in the project root directory.

    Returns:
        str: 'JavaScript', 'TypeScript', 'Python', 'Python & TypeScript', etc.
    """
    is_python = any(
        f in filenames
        for f in ["pyproject.toml", "uv.lock", "requirements.txt", "setup.py", "tox.ini", "Pipfile", "poetry.lock"]
    )

    is_typescript = "tsconfig.json" in filenames
    is_javascript = (
        any(
            f in filenames
            for f in ["package.json", "package-lock.json", "bun.lock", "yarn.lock", "pnpm-lock.yaml", "biome.json"]
        )
        or is_typescript
    )

    if is_python and is_typescript:
        return "Python & TypeScript"
    if is_python and is_javascript:
        return "Python & JavaScript"
    if is_python:
        return "Python"
    if is_typescript:
        return "TypeScript"
    if is_javascript:
        return "JavaScript"

    # Fallback to file extension check if root files are missing or ambiguous
    if any(f.endswith(".py") for f in filenames):
        return "Python (Files detected)"
    if any(f.endswith((".js", ".ts", ".jsx", ".tsx")) for f in filenames):
        return "JS/TS (Files detected)"

    return "Unknown"
