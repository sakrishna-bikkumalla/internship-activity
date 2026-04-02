# Use official Python slim image
FROM python:3.11-slim

# The uv binary is available as a separate image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory inside container
WORKDIR /app

# Copy dependency files and install
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy all application files
COPY . .

# Copy and set entrypoint script permissions
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Expose Streamlit default port
EXPOSE 8501

# Add the virtual environment's bin to PATH
ENV PATH="/app/.venv/bin:$PATH"

# Set entrypoint
ENTRYPOINT ["/entrypoint.sh"]
