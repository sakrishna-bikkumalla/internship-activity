#!/usr/bin/env bash
# Run locally with: ./run-local-ci.sh
# Or: bash run-local-ci.sh

set -euo pipefail

export CI_PROJECT_DIR="$(pwd)"
export PYTHON_VERSION="3.13"
export UV_CACHE_DIR="$CI_PROJECT_DIR/.uv-cache"
export UV_HTTP_TIMEOUT="600"
export UV_HTTP_RETRIES="10"
export PIP_DEFAULT_TIMEOUT="120"

echo "=== SETUP ==="
echo "--- setup_job ---"
python3 -V
if ! command -v uv >/dev/null 2>&1; then
  python3 -m pip install --no-cache-dir --retries 5 "uv==0.11.6"
fi
uv python install "$PYTHON_VERSION"
synced=0
for i in 1 2 3; do
  if uv sync --python "$PYTHON_VERSION" --all-extras --frozen --no-progress; then
    synced=1
    break
  fi
  if [ "$i" -lt 3 ]; then
    echo "uv sync failed, retrying in 5s..."
    sleep 5
  fi
done
if [ "$synced" -ne 1 ]; then
  echo "uv sync failed after 3 attempts"
  exit 1
fi
export VIRTUAL_ENV="$CI_PROJECT_DIR/.venv"
export PATH="$VIRTUAL_ENV/bin:$PATH"
python -V
uv tree --frozen > /dev/null

echo "=== LINT ==="
echo "--- lint_job ---"
uv run ruff check .
uv run ruff format --check .

echo "--- babel_job ---"
uv run pybabel extract . -o messages.pot
sed -i '/^"POT-Creation-Date:/d' messages.pot
if [ -n "$(git status --porcelain messages.pot)" ]; then
  echo "ERROR: messages.pot is outdated. Run: uv run pybabel extract . -o messages.pot, then commit the updated file."
  exit 1
fi

echo "=== TEST ==="
echo "--- test_job ---"
uv run pytest --cov=. --cov-report=term --cov-fail-under=80 tests/

echo "--- mypy ---"
uv run mypy --config-file mypy.ini src/gitlab_compliance_checker app.py

echo "--- vulture_job ---"
uv run vulture src/gitlab_compliance_checker app.py --min-confidence 100

echo "--- audit_job ---"
uv audit || true

echo "=== BUILD ==="
echo "--- build_job ---"
uv build
