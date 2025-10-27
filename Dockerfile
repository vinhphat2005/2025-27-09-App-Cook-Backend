FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt /app/requirements.txt

# Install Python packages with cache
RUN pip install --upgrade pip && \
    pip install -r /app/requirements.txt

# Copy application source
COPY . /app

EXPOSE 8000

# Use reload for dev. For production remove --reload and use a process manager.
CMD ["uvicorn", "main_async:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
