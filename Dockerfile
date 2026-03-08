FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for eventlet
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY portfolio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY portfolio/ .

# Create data directory
RUN mkdir -p data

# Expose port
EXPOSE 3000

# Run with eventlet
CMD ["python", "app.py"]

