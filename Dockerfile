FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8003

WORKDIR /app

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

EXPOSE 8003

# Honour the platform-provided $PORT (Container Apps sets it); default 8003.
CMD ["sh", "-c", "uvicorn planner.service:app --host 0.0.0.0 --port ${PORT:-8003}"]
