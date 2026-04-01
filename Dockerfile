# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY backend/requirements.txt backend/requirements.txt

# Install dependencies
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy the entire project
COPY . .

# Expose port (Railway will set PORT env var)
EXPOSE 8000

# Start command
CMD uvicorn backend.app:app --host 0.0.0.0 --port ${PORT:-8000}
