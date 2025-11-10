# EchoMind Backend - Production Dockerfile
# Solves blis compilation issue by controlling build environment

# Use Python 3.11 slim image (Debian-based, good compatibility)
FROM python:3.11-slim-bullseye

# Set working directory
WORKDIR /app

# Install system dependencies needed for compiling Python packages
# These are required for blis, spaCy, and other heavy NLP libraries
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    make \
    build-essential \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Upgrade pip and install Python dependencies
# This is where blis will compile successfully with our gcc setup
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Download spaCy language model (if needed)
# Uncomment the model you're using:
# RUN python -m spacy download en_core_web_sm
# RUN python -m spacy download en_core_web_md
# RUN python -m spacy download en_core_web_lg

# Copy application code
COPY . .

# Railway provides PORT environment variable
# We'll use it with a default fallback
ENV PORT=8000

# Expose the port
EXPOSE $PORT

# Health check (optional but good practice)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:$PORT/health')" || exit 1

# Run the application using uvicorn
# Railway will inject the PORT variable
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}
