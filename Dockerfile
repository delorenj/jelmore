FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
  gcc \
  postgresql-client \
  && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY pyproject.toml .
COPY src/ ./src/

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create logs directory
RUN mkdir -p /app/logs

EXPOSE 8687

CMD ["uvicorn", "src.tonzies.main:app", "--host", "0.0.0.0", "--port", "8687"]
