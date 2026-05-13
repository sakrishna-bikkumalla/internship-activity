import os
import re

mappings = [
    (r"\bgitlab_utils\b", "internship_activity_tracker.infrastructure.gitlab"),
    (r"\bProjects\b", "internship_activity_tracker.services.compliance"),
    (r"\bbatch_mode\b", "internship_activity_tracker.services.batch"),
    (r"\bissues\b", "internship_activity_tracker.services.issues"),
    (r"\buser_profile\b", "internship_activity_tracker.services.profile"),
    (r"\bmodes\b", "internship_activity_tracker.ui"),
]

# Special consolidation rules for UI (these should be checked after the general ones)
ui_consolidations = [
    (r"internship_activity_tracker\.ui\.batch_analytics", "internship_activity_tracker.ui.batch"),
    (r"internship_activity_tracker\.ui\.compliance_mode", "internship_activity_tracker.ui.compliance"),
    (r"internship_activity_tracker\.ui\.team_leaderboard", "internship_activity_tracker.ui.leaderboard"),
    (r"internship_activity_tracker\.ui\.user_profile", "internship_activity_tracker.ui.profile"),
    (r"internship_activity_tracker\.services\.compliance\.project_ui", "internship_activity_tracker.ui.compliance"),
    (r"internship_activity_tracker\.services\.batch\.batch_ui", "internship_activity_tracker.ui.batch"),
    (r"internship_activity_tracker\.services\.profile\.profile_ui", "internship_activity_tracker.ui.profile"),
    (r"internship_activity_tracker\.services\.profile\.render_user_profile", "internship_activity_tracker.ui.profile"),
    (r"internship_activity_tracker\.services\.issues\.issue_ui", "internship_activity_tracker.ui.issues"),
]

# Even more specific consolidations based on grep
direct_fixes = [
    (r"from issues import issue_ui", "from internship_activity_tracker.ui import issues as issue_ui"),
    (r"from modes import batch_analytics", "from internship_activity_tracker.ui import batch as batch_analytics"),
    (
        r"from modes import team_leaderboard",
        "from internship_activity_tracker.ui import leaderboard as team_leaderboard",
    ),
    (r"import modes\.team_leaderboard as tl", "import internship_activity_tracker.ui.leaderboard as tl"),
    (r"from modes import compliance_mode", "from internship_activity_tracker.ui import compliance as compliance_mode"),
    (r"from modes import user_profile", "from internship_activity_tracker.ui import profile as user_profile"),
]


def fix_imports(content):
    # Apply direct fixes first as they are most specific
    for old, new in direct_fixes:
        content = re.sub(old, new, content)

    # Apply consolidation rules next
    # We need to handle cases where they might have been partially transformed or were already using the intermediate form

    # Apply general mappings
    for old, new in mappings:
        # Avoid double mapping if it's already fixed
        if new in content:
            # This is tricky because content might contain both old and new.
            # Let's use negative lookahead/lookbehind if possible or just be careful.
            pass

        # We only want to replace if it's NOT already part of internship_activity_tracker
        content = re.sub(r"(?<!internship_activity_tracker\.)" + old, new, content)

    # Apply consolidation rules
    for old, new in ui_consolidations:
        content = re.sub(old, new, content)

    return content


def process_dir(dir_path):
    for root, _dirs, files in os.walk(dir_path):
        for file in files:
            if file.endswith(".py"):
                file_path = os.path.join(root, file)
                with open(file_path, "r") as f:
                    content = f.read()

                new_content = fix_imports(content)

                if new_content != content:
                    with open(file_path, "w") as f:
                        f.write(new_content)
                    print(f"Fixed: {file_path}")


if __name__ == "__main__":
    process_dir("src")
    process_dir("tests")
