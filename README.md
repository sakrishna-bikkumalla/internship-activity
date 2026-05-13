# Internship Activity Tracker

A Streamlit-based tool for tracking internship activities and performance via GitLab.

This project helps mentors and teams monitor intern progress, evaluate repository standards, and provide user-wise activity insights (commits, merge requests, issues, and time spent).

## Demo

- **Live Demo:** Not configured yet
- **Local Demo:** Run `streamlit run app.py` and open `http://localhost:8501`

## Features

- 👤 **User Profile Overview**
  - Personal vs contributed projects
  - Commit activity (including time-slot stats)
  - Groups, merge requests, and issues summary

- 🚀 **Compliance Audit (Unified)**
  - Username Input (Text Area or .txt File)
  - Unified report including General Stats, Authored Issue Quality, and Assigned MR Quality
  - High-performance extraction with minimum API calls
  - Comprehensive Excel report export

- 📦 **Docker-ready deployment**

## Project Structure

```text
internship-activity-tracker/
├── app.py
├── modes/
│   ├── user_profile.py
│   └── batch_analytics.py
├── gitlab_utils/
├── tests/
├── public/
├── assets/
├── pyproject.toml
├── uv.lock
├── Dockerfile
└── entrypoint.sh
```

## Requirements

- Python **3.11+**
- [uv](https://docs.astral.sh/uv/) (recommended) or `pip`
- GitLab Personal Access Token (with at least API read access)

## Installation (Local)

1. Clone the repository:

   ```bash
    git clone https://code.swecha.org/tools/internship-activity-tracker.git
    cd internship-activity-tracker
   ```

2. Install dependencies (using `uv`):

   ```bash
   uv sync
   ```

   *Alternatively, using `pip`:*

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install .
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
docker build -t internship-activity-tracker .
```

Run container:

```bash
docker run --rm -p 8501:8501 \
  -e GITLAB_URL="https://gitlab.com" \
  -e GITLAB_TOKEN="your_personal_access_token" \
  internship-activity-tracker
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
