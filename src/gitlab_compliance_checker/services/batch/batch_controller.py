from typing import Any, Dict, List

from gitlab_compliance_checker.services.batch.batch_service import process_single_project
from gitlab_compliance_checker.services.batch.export_service import prepare_export_data


def run_batch_for_projects(
    gl_client,
    project_ids: List[str],
    include_details: bool = True,
) -> Dict[str, Any]:
    """
    Main orchestration function for Batch Mode.

    Parameters:
        gl_client      : GitLab client instance
        project_ids    : List of project IDs or paths
        include_details: Whether to fetch detailed compliance info

    Returns:
        {
            "success": [...],
            "failed": [...],
            "summary": {...},
            "export_data": [...]
        }
    """

    results = []
    failures = []

    for project_id in project_ids:
        try:
            result = process_single_project(
                gl_client,
                project_id,
                include_details=include_details,
            )
            results.append(result)

        except Exception as e:
            failures.append(
                {
                    "project": project_id,
                    "error": str(e),
                }
            )

    summary = _generate_summary(results, failures)

    export_data = prepare_export_data(results)

    return {
        "success": results,
        "failed": failures,
        "summary": summary,
        "export_data": export_data,
    }


# ---------------- INTERNAL HELPERS ----------------


def _generate_summary(results: List[Dict], failures: List[Dict]) -> Dict[str, int]:
    """
    Generate summary statistics.
    """

    total = len(results) + len(failures)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = sum(1 for r in results if r.get("status") == "FAIL")
    errors = len(failures)

    return {
        "total_projects": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
    }
