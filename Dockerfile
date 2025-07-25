# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    # Essential build tools
    build-essential \
    pkg-config \
    # FFmpeg for audio processing
    ffmpeg \
    # Tesseract OCR for document processing
    tesseract-ocr \
    tesseract-ocr-eng \
    tesseract-ocr-urd \
    # Image processing libraries
    libjpeg-dev \
    libpng-dev \
    libtiff-dev \
    # PostgreSQL client
    libpq-dev \
    # Additional libraries
    libffi-dev \
    libssl-dev \
    # Git for some Python packages
    git \
    # Cleanup
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create directories for media and static files
RUN mkdir -p /app/media /app/staticfiles_collected

# Set correct permissions
RUN chmod +x /app/manage.py

# Collect static files (will be overridden in docker-compose)
RUN python manage.py collectstatic --noinput --clear || true

# Expose port
EXPOSE 8000

# Default command
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"] 