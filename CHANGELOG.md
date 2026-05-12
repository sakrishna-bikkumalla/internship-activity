# Changelog

All notable changes to this project will be documented in this file.

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/).

## [1.0.0] - 2026-04-17
### Added
- **Batch Analytics and Ranking**: Productivity tracking dashboard with team scoring, individual member rankings, GitLab-style 364-day activity heatmaps, achievement badges (rank badges, team player, sprint star, top committer, merge master, hackathon hero, consistency champ), collaboration percentages, and pie chart visualizations.
- **Compliance Audit**: Unified batch analysis mode consolidating ICFAI batch, RCTS batch, BAD MRs, and BAD Issues modes. Includes comprehensive quality metrics for MRs (no description, no linked issues, failed pipelines, no semantic commits, long merge times) and Issues (no labels, no milestone, long open time, no semantic title).
- **DX-Checker**: Developer experience scoring system analyzing project tooling across 5 dimensions: quality & linting tools (Ruff, MyPy, ESLint, Prettier, Vulture), security & secret scanning, testing & coverage enforcement, automation & CI/CD, and internationalization readiness.
- **BAD MRs/Issues Quality Tracking**: Quality metrics for closed/rejected MRs and closed issues, flagging items lacking proper documentation, labels, milestones, time tracking, semantic naming, and peer review.
- **Weekly Performance Tracker**: Integration with Corpus API (standup audio recording system) alongside GitLab activity, displaying audio players in a 7-day grid with combined GitLab/Corpus data.
- **Branch Selection**: Intermediate stage workflow allowing branch selection before running compliance analysis.
- **Project-wise Filtered Ranking**: Filter batch analytics and ranking results by specific GitLab projects.
- **Date Range Filtering**: Filter contributions by custom date ranges in both ranking and contribution mapping views.
- **Detailed Contribution Views**: Expanded MR titles, issue titles, and commit messages with GitLab links, plus activity feed sorted by date.
- **Specific Team View**: Dedicated view showing 6-column metrics dashboard (Commits, MR Merged, MR Open, MR Closed, Issues Raised, Issues Closed) with individual user performance tables.
- **Language-Aware CI Pipeline Recommendations**: DX-checker provides language-specific pipeline improvement suggestions.

### Changed
- **GitLab Client Migration**: Complete migration from python-gitlab to glabflow for native async GitLab API access. Removed aiohttp dependency, implemented persistent global event loop with background thread isolation to resolve Streamlit asyncio conflicts.
- **Package Management**: Replaced `requirements.txt` with `uv` package manager using `pyproject.toml` and `uv.lock` for deterministic, reproducible builds.
- **CI/CD Pipeline**: Removed branch restrictions to run on all commits, added shared `.venv` setup stage to eliminate redundant installs, implemented hybrid cached-sync strategy to fix 413 errors and disk space issues.
- **Code Quality Tooling**: Comprehensive pre-commit hooks including Ruff linting/formatting, MyPy static type checking, Vulture dead code detection (100% confidence), pytest coverage enforcement (80% minimum), and uv-audit dependency vulnerability scanning.
- **Compliance Service Refactoring**: Migrated compliance services to glabflow, reorganized into infrastructure/ui/services architecture.

### Fixed
- **Streamlit Asyncio Crashes**: Resolved event loop conflicts between Streamlit and async GitLab client by isolating glabflow operations in a background thread with dedicated event loop.
- **Commit Counting Accuracy**: Improved accuracy of commit fetching and counting, fixed issues with commit mixing between users.
- **Rate Limit Handling**: Added robust rate limit detection and exponential backoff retry logic for GitLab API calls.
- **SSL Configuration**: Unhardcoded SSL verification, now configurable via `GITLAB_SSL_VERIFY` environment variable.
- **Pipeline Analysis**: Improved CI/CD pipeline stage detection and tool identification, fixed language-aware recommendation generation.
- **Test Coverage**: Achieved 80%+ test coverage across all major modules with async-aware test mocks.

### Technical
- **Dependencies**: Streamlined from 11+ dependencies to 6 core dependencies (streamlit, xlsxwriter, glabflow, python-dotenv, plotly, pyyaml).
- **Type Safety**: Added MyPy with strict configuration (warn_return_any, strict_optional, no_implicit_optional).
- **Dead Code**: Added Vulture analysis excluding test files and venv directories.
- **Testing**: Added pytest-asyncio for async test support, comprehensive fixtures and mock patterns.

## [0.1.0] - 2025-07-28
### Added
- Core compliance checking logic.
- User profile README checker feature.
- Streamlit UI for interactive compliance reports.
- Docker support and deployment scripts.

### Fixed
- Bug fixes and error handling improvements.

### Changed
- Improved documentation and README clarity.

## [0.0.1] - 2025-06-15
- Prototype version with basic project and user compliance checks.
