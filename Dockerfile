FROM python:3.9-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    cmake \
    pkg-config \
    libx11-dev \
    libatlas-base-dev \
    libgtk-3-dev \
    libboost-python-dev \
    python3-dev \
    python3-pip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Set environment variables
ENV FLASK_APP=main.py
ENV FLASK_DEBUG=0
ENV PYTHONPATH=/app
ENV PORT=8080

# Create and activate virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy requirements first for better cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Create necessary directories with proper permissions
RUN mkdir -p /app/instance /app/backup /app/static/uploads/face_snapshots && \
    chmod 777 /app/instance /app/backup /app/static/uploads/face_snapshots

# Copy the rest of the application
COPY . .

# Remove any existing database
RUN rm -f /app/instance/attendance.db

# Set permissions for the application
RUN chown -R www-data:www-data /app && \
    chmod -R 755 /app && \
    chmod 777 /app/instance

# Switch to non-root user
USER www-data

# Initialize the database
RUN python init_db.py

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "main:app"]
