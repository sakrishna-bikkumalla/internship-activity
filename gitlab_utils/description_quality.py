import re


def analyze_description(text: str | None) -> dict:
    """
    Analyzes an MR description and assigns a quality score (0-100).
    Returns a dict with:
        - description_score (int)
        - quality_label (str: High, Moderate, Low)
        - feedback (list of str)
    """
    if not text or not text.strip():
        return {
            "description_score": 0,
            "quality_label": "Low",
            "feedback": ["No description provided"],
        }

    score = 0
    feedback = []
    text_lower = text.lower()

    # 1. Length points (Max +30)
    length = len(text.strip())
    if length >= 300:
        score += 30
    elif length >= 150:
        score += 20
        feedback.append("Description is a bit short, could provide more detail.")
    elif length >= 50:
        score += 10
        feedback.append("Description is very short.")
    else:
        feedback.append("Description is extremely short, lacks detail.")

    # 2. Structured Sections (Max +20)
    # Check for markdown headers like # Summary, ## Changes, **Impact**, etc.
    if re.search(r"(#+ |\*\*).*(summary|changes|impact|testing|context|description)", text_lower):
        score += 20
    else:
        feedback.append("Missing structured sections (e.g., Summary, Changes, Impact).")

    # 3. Action Verbs (Max +15)
    action_verbs = ["added", "fixed", "updated", "removed", "refactored", "implemented", "resolved"]
    if any(verb in text_lower for verb in action_verbs):
        score += 15
    else:
        feedback.append("Could uniquely describe what changed using clear action verbs.")

    # 4. Context/Impact (Max +15)
    context_keywords = [
        "because",
        "so that",
        "in order to",
        "fix",
        "resolves",
        "closes",
        "issue",
        "impact",
    ]
    if any(keyword in text_lower for keyword in context_keywords):
        score += 15
    else:
        feedback.append("Lacks explanation of *why* this change is needed or its impact.")

    # 5. Has a list (Max +10)
    # Checks for markdown lists: '- ', '* ', '1. '
    if re.search(r"(^|\n)\s*([-*]|\d+\.)\s+", text):
        score += 10
    else:
        feedback.append("Consider using lists to break down multiple changes.")

    # 6. Not a vague/keyword-only description (Max +10)
    vague_phrases = ["fix", "wip", "changes", "update", "done", "test"]
    if length > 20 and text_lower.strip() not in vague_phrases:
        score += 10
    elif text_lower.strip() in vague_phrases:
        # Penalize if it's literally just "fix" or "wip"
        feedback.append("Description is too vague/generic.")

    # Cap score at 100
    score = min(score, 100)

    # Edge case: If text is huge but has zero structure/keywords (lorem ipsum style)
    if length > 500 and score < 50:
        feedback.insert(0, "Description is long but lacks structure and key MR context.")

    # Determine Label
    if score >= 80:
        label = "High"
    elif score >= 50:
        label = "Moderate"
    else:
        label = "Low"

    # Limit feedback items to top 2 to keep UI clean
    final_feedback = " | ".join(feedback[:2]) if feedback else "Good description"
    if score == 100:
        final_feedback = "Excellent description"

    return {
        "description_score": score,
        "quality_label": label,
        "feedback": final_feedback,
    }
