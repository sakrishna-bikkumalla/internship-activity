from internship_activity_tracker.infrastructure.gitlab.description_quality import analyze_description


def test_empty_description():
    """Empty description should get 0 score and Low quality."""
    result = analyze_description(None)
    assert result["description_score"] == 0
    assert result["quality_label"] == "Low"
    assert "No description provided" in result["feedback"]

    result = analyze_description("   ")
    assert result["description_score"] == 0


def test_high_quality_description():
    """A structured, detailed description with action verbs and lists."""
    desc = """
    ## Summary
    This MR fixes the login bug where users were redirected to a 404 page.

    ## Changes
    - Updated authentication controller
    - Added unit tests for login failure cases

    ## Impact
    Resolves issue #42 so that users can log in successfully without errors.
    """
    result = analyze_description(desc)
    assert result["description_score"] >= 80
    assert result["quality_label"] == "High"


def test_moderate_quality_description():
    """A basic description with some length and an action verb but lacking structure."""
    desc = "Fixed the database migration issue where indices were not created properly."
    result = analyze_description(desc)
    assert result["description_score"] >= 25
    assert result["description_score"] <= 79
    assert result["quality_label"] == "Low" or result["quality_label"] == "Moderate"


def test_low_quality_description():
    """Very short, vague description."""
    desc = "update Readme file"
    result = analyze_description(desc)
    assert result["description_score"] < 50
    assert result["quality_label"] == "Low"


def test_keyword_only_description():
    """Keyword-only description."""
    desc = "fix"
    result = analyze_description(desc)
    assert result["description_score"] < 25
    assert result["quality_label"] == "Low"


def test_large_irrelevant_text():
    """A large block of text without MR structures or keywords."""
    desc = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 20
    result = analyze_description(desc)
    assert result["description_score"] == 40
    assert result["quality_label"] == "Low"
    assert "Description is long but lacks structure and key MR context." in result["feedback"]


def test_structured_description():
    """Sections and lists."""
    desc = """
    ### Context
    In order to improve performance.

    ### Changes
    1. Added cache
    2. Refactored queries
    """
    result = analyze_description(desc)
    assert result["description_score"] >= 80
    assert result["quality_label"] == "High"


def test_perfect_quality_description():
    """Achieve a score of 100."""
    desc = (
        """
    ## Summary
    This MR is implemented because we need to fix the issue of slow loading.
    It added several optimizations in order to resolve the impact on users.
    - Optimized database queries
    - Added caching layer
    - Removed redundant loops
    """
        + "x" * 400
    )
    result = analyze_description(desc)
    assert result["description_score"] == 100
    assert result["feedback"] == "Excellent description"
