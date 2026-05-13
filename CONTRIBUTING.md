# Contributing to internship-activity-tracker

Thank you for your interest in contributing to **internship-activity-tracker**! We welcome contributions of all kinds including bug reports, feature requests, documentation improvements, and code submissions.

## How to Report Issues

- Before opening a new issue, please search existing issues to avoid duplicates.
- When creating an issue, **please use the provided [Issue Template](.gitlab/issue_template.md)**.
  This template helps you provide all necessary details such as:
  - Clear and detailed bug reproduction steps
  - Environment information (tool version, Python version, OS)
  - Screenshots or logs if applicable

  The issue template streamlines triaging and helps maintainers diagnose problems quickly.

## Suggesting Features

- Open a new issue labeled `feature-request`.
- Please use the **[Issue Template](.gitlab/issue_template.md)** to describe the feature and its intended usage clearly.

## Code Contributions

- Fork the repository and create a branch from `main`.
- Follow the existing coding style and use [PEP 8](https://pep8.org/) conventions.
- Write descriptive commit messages following [Conventional Commits](https://www.conventionalcommits.org/):
  - `feat:` for new features
  - `fix:` for bug fixes
  - `docs:` for documentation changes
  - `chore:` for maintenance and tooling changes
- Add tests for new features or bug fixes.
- Run linters and tests before submitting a merge request.

- When submitting a merge request, please use the **[Merge Request Template](.gitlab/mr_template.md)**.
  This ensures you provide all necessary information such as:
  - Description of changes
  - Related issues (with Closes #issue_number if applicable)
  - Type of change (patch, feature, breaking)
  - Test status and checklist compliance

## Pull Request Process

- Submit a merge request targeting the `main` branch with all requested details filled in the template.
- Clearly state the semantic versioning impact in the merge request description.
- Respond to review feedback promptly.
- Ensure all continuous integration checks pass.

## Local Development Setup

### Setting Up Pre-commit Hooks

We use `pre-commit` to automatically run code quality checks before each commit:

1. **Install dependencies (including pre-commit)**:
   ```bash
   uv sync --all-extras
   ```

2. **Install the git hooks** (including conventional commit linting):
   ```bash
   uv run pre-commit install
   uv run pre-commit install --hook-type commit-msg
   ```

3. **Run hooks manually** (optional):
   ```bash
   uv run pre-commit run --all-files  # Run on all files
   uv run pre-commit run              # Run on staged files
   ```

### Running Individual Checks

If you want to run specific tools directly or via pre-commit without running the entire suite, you can use these commands:

| Tool | Pre-commit Hook | Standalone Tool Command |
| :--- | :--- | :--- |
| **Ruff (Lint)** | `uv run pre-commit run ruff --all-files` | `uv run ruff check .` |
| **Ruff (Format)** | `uv run pre-commit run ruff-format --all-files` | `uv run ruff format .` |
| **Mypy** | `uv run pre-commit run mypy --all-files` | `uv run mypy --config-file mypy.ini .` |
| **Vulture** | `uv run pre-commit run vulture --all-files` | `uv run vulture gitlab_utils/ modes/ Projects/ app.py --min-confidence 100` |
| **UV Audit** | `uv run pre-commit run uv-audit --all-files` | `uv audit` |
| **Babel** | `uv run pre-commit run babel-extract --all-files` | `uv run pybabel extract . -o messages.pot --no-creation-date` |
| **Test Coverage** | N/A | `uv run pytest --cov --cov-report=term-missing` |

### Running Tests

Run tests locally before creating a merge request. You can run the entire suite or target specific areas:

| Test Target | Command |
| :--- | :--- |
| **All Tests** | `uv run pytest` |
| **Verbose Output** | `uv run pytest -v` |
| **Stop on First Failure** | `uv run pytest -x` |
| **Specific Directory** | `uv run pytest tests/` |
| **Specific File** | `uv run pytest tests/test_app.py` |

## Code of Conduct

Please read and follow the [Code of Conduct](CODE_OF_CONDUCT.md) to foster a welcoming and respectful community.

---

Thank you for helping to improve **internship-activity-tracker**!

---

### Helpful Links

- [Issue Template](.gitlab/issue_template.md)
- [Merge Request Template](.gitlab/mr_template.md)
