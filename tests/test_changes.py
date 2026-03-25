
"""
Test script to verify the changes made to app.py:
1. File categories functionality is removed
2. Suggested missing items appear for all projects
3. README scores appear for every project
"""

import re
import sys


def test_file_categories_removed():
    """Test that file categories functionality has been removed."""
    with open("app.py", "r") as f:
        content = f.read()

    # Check that the file categories section is removed from the UI
    categories_pattern = r'"5\. 🗂️ File Categories":'
    assert not re.search(categories_pattern, content), "File categories section still present in UI"

    # Check that file categories export section is removed
    export_pattern = r"# --- Repository file categories & export for single project ---"
    assert not re.search(export_pattern, content), "File categories export section still present"


def test_suggestions_for_all_projects():
    """Test that suggestions appear for all projects."""
    with open("modes/compliance_mode.py", "r") as f:
        content = f.read()

    # Check that the suggestion logic doesn't have any project-specific filters
    suggestion_logic = re.search(
        r"if not report\.get\(",
        content,
        re.MULTILINE | re.DOTALL,
    )

    assert suggestion_logic, "Could not find suggestion logic"

    # Check that there are no project-specific filters in the suggestion function
    suggestion_function = re.search(
        r"def get_suggestions_for_missing_items\(report\):(.*?)(?=def|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if suggestion_function:
        suggestion_code = suggestion_function.group(1)
        # Look for any project-specific filtering logic
        project_filters = [
            r"if.*project.*:",
            r"if.*repository.*:",
            r"if.*namespace.*:",
        ]

        for filter_pattern in project_filters:
            assert not re.search(filter_pattern, suggestion_code, re.IGNORECASE), f"Found project-specific filter in suggestions: {filter_pattern}"


def test_readme_scores_for_all_projects():
    """Test that README scores appear for every project."""
    with open("modes/compliance_mode.py", "r") as f:
        content = f.read()

    # Check that readme_status is always set in the compliance check (checking whole file)
    readme_status_assignments = re.findall(
        r'report\[["\']readme_status["\']\]\s*=\s*["\']([^"\']+)["\']', content
    )

    assert len(readme_status_assignments) >= 2, f"Not enough readme_status assignments found: {readme_status_assignments}"

    expected_statuses = {"present", "empty", "missing"}
    actual_statuses = set(readme_status_assignments)

    assert expected_statuses.issubset(actual_statuses), f"Missing expected readme_status values. Expected: {expected_statuses}, Found: {actual_statuses}"


def test_suggestions_called_for_all_projects():
    """Test that suggestions are called for all projects with missing items."""
    with open("modes/compliance_mode.py", "r") as f:
        content = f.read()

    # Check that get_suggestions_for_missing_items is called in the main compliance flow
    suggestion_calls = re.findall(r"get_suggestions_for_missing_items\(report\)", content)

    assert len(suggestion_calls) >= 2, f"Not enough calls to get_suggestions_for_missing_items found: {len(suggestion_calls)}"


def main():
    """Run all tests."""
    print("Testing changes to app.py...")
    print("=" * 50)

    tests = [
        test_file_categories_removed,
        test_suggestions_for_all_projects,
        test_readme_scores_for_all_projects,
        test_suggestions_called_for_all_projects,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            test()
            passed += 1
            print(f"✅ PASS: {test.__name__}")
        except AssertionError as e:
            print(f"❌ FAIL: {test.__name__} - {str(e)}")
        except Exception as e:
            print(f"⚠️ ERROR: {test.__name__} - {str(e)}")
        print()

    print("=" * 50)
    print(f"Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! The changes have been successfully implemented.")
        return 0
    else:
        print("❌ Some tests failed. Please review the implementation.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
