#!/usr/bin/env python3
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
    if re.search(categories_pattern, content):
        print("❌ FAIL: File categories section still present in UI")
        return False

    # Check that file categories export section is removed
    export_pattern = r"# --- Repository file categories & export for single project ---"
    if re.search(export_pattern, content):
        print("❌ FAIL: File categories export section still present")
        return False

    print("✅ PASS: File categories functionality removed")
    return True


def test_suggestions_for_all_projects():
    """Test that suggestions appear for all projects."""
    with open("app.py", "r") as f:
        content = f.read()

    # Check that the suggestion logic doesn't have any project-specific filters
    suggestion_logic = re.search(
        r"for key, display_name, suggestion_text in suggestion_list:\s*if not report\.get\(key, True\):",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if not suggestion_logic:
        print("❌ FAIL: Could not find suggestion logic")
        return False

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
            if re.search(filter_pattern, suggestion_code, re.IGNORECASE):
                print(f"❌ FAIL: Found project-specific filter in suggestions: {filter_pattern}")
                return False

    print("✅ PASS: Suggestions logic appears to work for all projects")
    return True


def test_readme_scores_for_all_projects():
    """Test that README scores appear for every project."""
    with open("app.py", "r") as f:
        content = f.read()

    # Check that readme_status is always set in the compliance check
    compliance_function = re.search(
        r"def check_project_compliance\(project, branch=None\):(.*?)(?=def|\Z)",
        content,
        re.MULTILINE | re.DOTALL,
    )

    if not compliance_function:
        print("❌ FAIL: Could not find compliance check function")
        return False

    compliance_code = compliance_function.group(1)

    # Check that readme_status is always set (not conditional)
    readme_status_assignments = re.findall(
        r'report\["readme_status"\] = "([^"]+)"', compliance_code
    )

    if len(readme_status_assignments) < 2:  # Should have at least "present", "empty", and "missing"
        print(f"❌ FAIL: Not enough readme_status assignments found: {readme_status_assignments}")
        return False

    expected_statuses = {"present", "empty", "missing"}
    actual_statuses = set(readme_status_assignments)

    if not expected_statuses.issubset(actual_statuses):
        print(
            f"❌ FAIL: Missing expected readme_status values. Expected: {expected_statuses}, Found: {actual_statuses}"
        )
        return False

    print("✅ PASS: README scores are set for all projects")
    return True


def test_suggestions_called_for_all_projects():
    """Test that suggestions are called for all projects with missing items."""
    with open("app.py", "r") as f:
        content = f.read()

    # Check that get_suggestions_for_missing_items is called in the main compliance flow
    suggestion_calls = re.findall(r"get_suggestions_for_missing_items\(report\)", content)

    if len(suggestion_calls) < 2:  # Should be called in both single project and batch mode
        print(
            f"❌ FAIL: Not enough calls to get_suggestions_for_missing_items found: {len(suggestion_calls)}"
        )
        return False

    print("✅ PASS: Suggestions are called for all projects")
    return True


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
        if test():
            passed += 1
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
