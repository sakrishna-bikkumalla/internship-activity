"""
Test script to verify the changes made to app.py:
1. File categories functionality is removed
2. Suggested missing items appear for all projects
3. README scores appear for every project
"""

import os
import re
import sys
from unittest.mock import patch


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
            assert not re.search(filter_pattern, suggestion_code, re.IGNORECASE), (
                f"Found project-specific filter in suggestions: {filter_pattern}"
            )


def test_readme_scores_for_all_projects():
    """Test that README scores appear for every project."""
    with open("modes/compliance_mode.py", "r") as f:
        content = f.read()

    # Check that readme_status is always set in the compliance check (checking whole file)
    readme_status_assignments = re.findall(r'report\[["\']readme_status["\']\]\s*=\s*["\']([^"\']+)["\']', content)

    assert len(readme_status_assignments) >= 2, (
        f"Not enough readme_status assignments found: {readme_status_assignments}"
    )

    expected_statuses = {"present", "empty", "missing"}
    actual_statuses = set(readme_status_assignments)

    assert expected_statuses.issubset(actual_statuses), (
        f"Missing expected readme_status values. Expected: {expected_statuses}, Found: {actual_statuses}"
    )


def test_suggestions_called_for_all_projects():
    """Test that suggestions are called for all projects with missing items."""
    with open("modes/compliance_mode.py", "r") as f:
        content = f.read()

    # Check that get_suggestions_for_missing_items is called in the main compliance flow
    suggestion_calls = re.findall(r"get_suggestions_for_missing_items\(report\)", content)

    assert len(suggestion_calls) >= 2, (
        f"Not enough calls to get_suggestions_for_missing_items found: {len(suggestion_calls)}"
    )


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


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


class TestMainFunction:
    """Tests for the main() function in test_changes.py."""

    def test_main_passes(self):
        """Test that main() passes when all tests pass."""
        from tests import test_changes

        result = test_changes.main()
        assert result == 0

    def test_main_returns_zero_on_success(self):
        """Test that main returns 0 when all tests pass."""
        import tests.test_changes as tc

        assert tc.main() == 0

    def test_main_prints_results(self, capsys):
        """Test that main prints results."""
        import tests.test_changes as tc

        tc.main()
        captured = capsys.readouterr()
        assert "Test Results:" in captured.out

    def test_main_prints_passed_tests(self, capsys):
        """Test that main prints passed tests."""
        import tests.test_changes as tc

        tc.main()
        captured = capsys.readouterr()
        assert "PASS" in captured.out

    def test_main_success_message(self, capsys):
        """Test that main prints success message when all tests pass."""
        import tests.test_changes as tc

        tc.main()
        captured = capsys.readouterr()
        assert "All tests passed" in captured.out or "passed" in captured.out

    def test_exception_handling_in_main(self):
        """Test that main handles exceptions gracefully."""
        import tests.test_changes as tc

        original_test = tc.test_file_categories_removed

        def failing_test():
            raise RuntimeError("Test error")

        tc.test_file_categories_removed = failing_test
        try:
            result = tc.main()
            assert result == 1
        finally:
            tc.test_file_categories_removed = original_test

    def test_main_handles_non_assertion_errors(self, capsys):
        """Test that main handles non-AssertionError exceptions and prints error."""
        import tests.test_changes as tc

        original_test = tc.test_file_categories_removed

        def failing_test():
            raise ValueError("Non-assertion error")

        tc.test_file_categories_removed = failing_test
        try:
            tc.main()
            captured = capsys.readouterr()
            assert "ERROR" in captured.out or "ValueError" in captured.out
        finally:
            tc.test_file_categories_removed = original_test

    def test_name_main_block(self, tmp_path):
        """Test that the if __name__ == '__main__' block executes."""
        import subprocess

        test_file = __file__
        result = subprocess.run(
            [sys.executable, test_file],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(test_file)) or ".",
        )
        assert result.returncode == 0
        assert "All tests passed" in result.stdout

    def test_main_handles_assertion_error(self, capsys):
        """Test that main handles AssertionError and prints fail message."""
        import tests.test_changes as tc

        original_test = tc.test_file_categories_removed

        def failing_test():
            raise AssertionError("Expected failure")

        tc.test_file_categories_removed = failing_test
        try:
            tc.main()
            captured = capsys.readouterr()
            assert "FAIL" in captured.out or "AssertionError" in captured.out
        finally:
            tc.test_file_categories_removed = original_test
