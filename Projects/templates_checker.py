from typing import Any, Dict, Optional


def check_templates(gl, project_id: int, ref: Optional[str] = None) -> Dict[str, Any]:
    """
    Detailed GitLab templates checker for issues and MRs.
    """
    try:
        project = gl.projects.get(project_id)
        branch = ref or getattr(project, "default_branch", "main")

        result = {
            "issue_templates_folder": False,
            "issue_template_files": [],
            "merge_request_templates_folder": False,
            "merge_request_template_files": [],
            "exists": False,
        }

        # Check Issue Templates
        try:
            items = project.repository_tree(path=".gitlab/issue_templates", ref=branch)
            md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
            if md_files:
                result["issue_templates_folder"] = True
                result["issue_template_files"] = md_files
                result["exists"] = True
        except Exception:
            pass

        # Check Merge Request Templates
        try:
            items = project.repository_tree(path=".gitlab/merge_request_templates", ref=branch)
            md_files = [item["name"] for item in items if item["name"].lower().endswith(".md")]
            if md_files:
                result["merge_request_templates_folder"] = True
                result["merge_request_template_files"] = md_files
                result["exists"] = True
        except Exception:
            pass

        return result
    except Exception as e:
        return {"error": str(e)}
