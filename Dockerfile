# Use a secure, minimal official Python Alpine base image
FROM python:3.10-alpine

# Install runtime dependencies for lxml and pandas execution
RUN apk add --no-cache libxml2 libxslt libstdc++

# Install temporary build dependencies to compile C extensions if wheels are not cached
RUN apk add --no-cache --virtual .build-deps \
    build-base \
    gcc \
    g++ \
    musl-dev \
    libxml2-dev \
    libxslt-dev \
    python3-dev

# Set up working directory inside the container
WORKDIR /app

# Copy requirements file first to take advantage of Docker build caching layers
COPY requirements.txt .

# Install dependencies and Gunicorn (production WSGI server)
RUN pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir gunicorn

# Clean up temporary build dependencies to keep the Alpine footprint extremely small
RUN apk del .build-deps

# Copy the entire app source directory into the container
COPY app/ .

# Expose the default Flask/Gunicorn port
EXPOSE 5000

# Run Gunicorn with multi-threaded workers for production performance
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", "--threads", "4", "--timeout", "120", "app:app"]
