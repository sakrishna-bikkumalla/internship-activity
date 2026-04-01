# GitLab Compliance Checker

A Streamlit-based tool for checking GitLab repository compliance and generating user analytics.

This project helps teams and mentors quickly evaluate whether repositories follow expected standards (documentation, license, IDE config, templates, metadata), and also provides user-wise activity insights (projects, commits, groups, issues, merge requests).

## Demo

- **Live Demo:** Not configured yet
- **Local Demo:** Run `streamlit run app.py` and open `http://localhost:8501`

## Features

- ✅ **Project Compliance Checks**
  - README / CONTRIBUTING / CHANGELOG presence
  - LICENSE validation (AGPLv3-focused)
  - `.gitignore`, `pyproject.toml`, `uv.lock`
  - `.vscode` setup checks (`settings.json`, `extensions.json`, etc.)
  - Issue & merge request template presence
  - Project description and tags checks

- 👤 **User Profile Overview**
  - Personal vs contributed projects
  - Commit activity (including time-slot stats)
  - Groups, merge requests, and issues summary

- 🚀 **Batch Analytics Modes**
  - Batch 2026 ICFAI
  - Batch 2026 RCTS
  - Excel report export

- 📦 **Docker-ready deployment**

## Project Structure

```text
gitlab-compliance-checker/
├── app.py
├── modes/
│   ├── compliance_mode.py
│   ├── user_profile.py
│   └── batch_mode.py
├── gitlab_utils/
├── tests/
├── public/
├── assets/
├── requirements.txt
├── Dockerfile
└── entrypoint.sh
```

## Requirements

- Python **3.11+**
- GitLab Personal Access Token (with at least API read access)

## Installation (Local)

1. Clone the repository:

   ```bash
   git clone https://code.swecha.org/tools/gitlab-compliance-checker.git
   cd gitlab-compliance-checker
   ```

2. Create and activate a virtual environment:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

## Configuration

Set credentials using either `.env` (local dev) or `.streamlit/secrets.toml`.

### How to Create a GitLab Personal Access Token

1. Sign in to your GitLab account.
2. Go to **User Settings → Access Tokens**.
3. Enter a token name (example: `compliance-checker-token`).
4. Select an expiry date (recommended).
5. Choose scopes (minimum recommended: `read_api`; if needed, use `api`).
6. Click **Create personal access token**.
7. Copy the token immediately and store it safely (GitLab shows it only once).

> ⚠️ Do not commit your token to git. Keep it only in local `.env`, `.streamlit/secrets.toml`, or environment variables.

### Token Creation Process (Quick)

```text
GitLab Login
  -> User Settings
  -> Access Tokens
  -> Name + Expiry + Scope (read_api/api)
  -> Create token
  -> Copy token once
  -> Paste in .env or .streamlit/secrets.toml
```

### Option 1: `.env`

```env
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_personal_access_token
```

Create the `.env` file in project root:

```bash
cat > .env << 'EOF'
GITLAB_URL=https://gitlab.com
GITLAB_TOKEN=your_personal_access_token
EOF
```

### Option 2: `.streamlit/secrets.toml`

```toml
GITLAB_URL="https://gitlab.com"
GITLAB_TOKEN="your_personal_access_token"
```

## Run the App

```bash
streamlit run app.py
```

Open in browser: `http://localhost:8501`

## Docker Usage

Build image:

```bash
docker build -t gitlab-compliance-checker .
```

Run container:

```bash
docker run --rm -p 8501:8501 \
  -e GITLAB_URL="https://gitlab.com" \
  -e GITLAB_TOKEN="your_personal_access_token" \
  gitlab-compliance-checker
```

## Testing

Run unit tests:

```bash
pytest
```

## Development Notes

- Main entry point: `app.py`
- UI modes live in `modes/`
- GitLab API wrappers/utilities are in `gitlab_utils/`
- High-performance async scanning is built into `GitLabClient`
- Additional verification scripts:
  - `verify_data.py`
  - `diagnose_review.py`

## Documentation & Governance

- [CHANGELOG](CHANGELOG.md)
- [CONTRIBUTING](CONTRIBUTING.md)
- [CODE OF CONDUCT](CODE_OF_CONDUCT.md)
- [LICENSE](LICENSE)

## License

This project is licensed under **GNU Affero General Public License v3.0**.
