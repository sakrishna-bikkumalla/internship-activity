import os
import re

mappings = [
    (r"\bgitlab_utils\b", "gitlab_compliance_checker.infrastructure.gitlab"),
    (r"\bProjects\b", "gitlab_compliance_checker.services.compliance"),
    (r"\bbatch_mode\b", "gitlab_compliance_checker.services.batch"),
    (r"\bissues\b", "gitlab_compliance_checker.services.issues"),
    (r"\buser_profile\b", "gitlab_compliance_checker.services.profile"),
    (r"\bmodes\b", "gitlab_compliance_checker.ui"),
]

# Special consolidation rules for UI (these should be checked after the general ones)
ui_consolidations = [
    (r"gitlab_compliance_checker\.ui\.batch_analytics", "gitlab_compliance_checker.ui.batch"),
    (r"gitlab_compliance_checker\.ui\.compliance_mode", "gitlab_compliance_checker.ui.compliance"),
    (r"gitlab_compliance_checker\.ui\.team_leaderboard", "gitlab_compliance_checker.ui.leaderboard"),
    (r"gitlab_compliance_checker\.ui\.user_profile", "gitlab_compliance_checker.ui.profile"),
    (r"gitlab_compliance_checker\.services\.compliance\.project_ui", "gitlab_compliance_checker.ui.compliance"),
    (r"gitlab_compliance_checker\.services\.batch\.batch_ui", "gitlab_compliance_checker.ui.batch"),
    (r"gitlab_compliance_checker\.services\.profile\.profile_ui", "gitlab_compliance_checker.ui.profile"),
    (r"gitlab_compliance_checker\.services\.profile\.render_user_profile", "gitlab_compliance_checker.ui.profile"),
    (r"gitlab_compliance_checker\.services\.issues\.issue_ui", "gitlab_compliance_checker.ui.issues"),
]

# Even more specific consolidations based on grep
direct_fixes = [
    (r"from issues import issue_ui", "from gitlab_compliance_checker.ui import issues as issue_ui"),
    (r"from modes import batch_analytics", "from gitlab_compliance_checker.ui import batch as batch_analytics"),
    (r"from modes import team_leaderboard", "from gitlab_compliance_checker.ui import leaderboard as team_leaderboard"),
    (r"import modes\.team_leaderboard as tl", "import gitlab_compliance_checker.ui.leaderboard as tl"),
    (r"from modes import compliance_mode", "from gitlab_compliance_checker.ui import compliance as compliance_mode"),
    (r"from modes import user_profile", "from gitlab_compliance_checker.ui import profile as user_profile"),
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

        # We only want to replace if it's NOT already part of gitlab_compliance_checker
        content = re.sub(r"(?<!gitlab_compliance_checker\.)" + old, new, content)

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
