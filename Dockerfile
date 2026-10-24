# Use official lightweight Python image
FROM python:3.11-slim

# Prevent Python from writing .pyc files and enable unbuffered logging
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install dependencies first for Docker caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY main.py .
COPY static/ static/

# Run as non-privileged user for security
RUN useradd -u 8888 appuser && chown -R appuser:appuser /app
USER appuser

# Expose Cloud Run default port
EXPOSE 8080

# Launch server dynamically binding to GCP $PORT
CMD exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}
