FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  gcc \
  postgresql-client \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better layer caching
COPY pyproject.toml .

# Install Python dependencies (not editable in container)
RUN pip install --no-cache-dir fastapi>=0.115.0 uvicorn[standard]>=0.32.0 sqlalchemy>=2.0.0 alembic>=1.13.0 asyncpg>=0.30.0 redis>=5.2.0 nats-py>=2.10.0 pydantic>=2.10.0 pydantic-settings>=2.0.0 python-dotenv>=1.0.0 httpx>=0.28.0 websockets>=14.0 structlog>=24.0.0 python-multipart>=0.0.20

# Copy source code
COPY src/ ./src/

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8687

CMD ["uvicorn", "src.jelmore.main:app", "--host", "0.0.0.0", "--port", "8687"]
