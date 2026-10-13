FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure config and downloads directories are writable
RUN mkdir -p /app/config /app/downloads && chmod 1777 /app/config /app/downloads

EXPOSE 9876

# Set PYTHONPATH to include /app
ENV PYTHONPATH=/app

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "9876"]
