FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \ 
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies first to leverage Docker layer caching
COPY requirements.txt /app/requirements.txt
RUN pip install -r requirements.txt

# Copy application code
COPY . /app

# Create non-root user for improved security
RUN groupadd -r app && useradd -r -g app -m -d /home/app app && \
    chown -R app:app /app && \
    chown -R app:app /home/app && \
    mkdir -p /home/app/.config && \
    chown -R app:app /home/app/.config
USER app

# Default command can be overridden by docker-compose
CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]

