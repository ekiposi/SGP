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
ENV FLASK_ENV=production
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
RUN mkdir -p instance backup static/uploads/face_snapshots && \
    chmod 777 instance backup static/uploads/face_snapshots

# Copy the rest of the application
COPY . .

# Set permissions for the application
RUN chown -R www-data:www-data /app && \
    chmod -R 755 /app

# Switch to non-root user
USER www-data

# Initialize the database
RUN python init_db.py || true

# Expose port
EXPOSE 8080

# Command to run the application
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "4", "--timeout", "120", "main:application"]
