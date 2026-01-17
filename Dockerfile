FROM python:3.11-slim

# Install system dependencies including FFmpeg, build tools for pycairo, and Playwright deps
# Updated for Railway build context - using trevnoctilla-backend/ prefix
# Force rebuild - Railway cache issue
RUN apt-get update && apt-get install -y \
    ffmpeg \
    gcc \
    python3-dev \
    pkg-config \
    libcairo2-dev \
    wget \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright system dependencies and browsers
# This installs all required libraries for Chromium to run
RUN playwright install-deps chromium && \
    playwright install chromium

# Copy application code
COPY . .

# Create necessary directories
RUN mkdir -p uploads edited saved_html converted_videos converted_audio

# Make start script executable
RUN chmod +x start.sh

# Expose port
EXPOSE 5000

# Run the application using start script
CMD ["./start.sh"]
