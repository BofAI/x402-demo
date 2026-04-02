# x402-tron-demo: Python server
FROM python:3.12-slim

# Install build dependency required by pip git URLs
RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy requirements.txt first for better caching
COPY requirements.txt /app/requirements.txt

# Create virtual environment and install Python dependencies
RUN python -m venv /app/.venv && \
    /app/.venv/bin/pip install --upgrade pip && \
    /app/.venv/bin/pip install -r /app/requirements.txt

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PATH="/app/.venv/bin:$PATH"

# Copy Python service code
COPY server/ /app/server/

# Create logs directory
RUN mkdir -p /app/logs

# Expose ports
# 8000: server
EXPOSE 8000

CMD ["bash", "-c", "python /app/server/main.py 2>&1 | tee -a /app/logs/server.log"]
