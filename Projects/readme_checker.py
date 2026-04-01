import base64
from typing import Any, Dict


def check_readme(gl, project_id: int) -> Dict[str, Any]:
    """
    Detailed README checker: existence, size, and essential sections.
    """
    try:
        project = gl.projects.get(project_id)
        branch = getattr(project, "default_branch", "main")

        readme_variants = ["README.md", "README", "README.txt"]
        content = ""
        found_file = ""

        for variant in readme_variants:
            try:
                f = project.files.get(file_path=variant, ref=branch)
                content = base64.b64decode(f.content).decode("utf-8")
                found_file = variant
                break
            except Exception:
                continue

        if not content:
            return {"exists": False, "status": "Missing README", "needs_improvement": True}

        lc = content.lower()
        expected_sections = [
            "installation",
            "usage",
            "getting started",
            "setup",
            "license",
            "contributing",
            "example",
            "quick start",
            "features",
        ]
        found_sections = [s for s in expected_sections if s in lc]

        needs_improvement = len(found_sections) < 3 or len(content.strip()) < 150

        return {
            "exists": True,
            "status": "README present",
            "file": found_file,
            "sections_found": found_sections,
            "needs_improvement": needs_improvement,
            "content_length": len(content.strip()),
        }

    except Exception as e:
        return {"exists": False, "status": f"Error: {e}", "needs_improvement": True}
