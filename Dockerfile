FROM python:3.12-slim

# Node.js required for pmxt sidecar server
RUN apt-get update && apt-get install -y nodejs npm && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

COPY prediction_mirror/ prediction_mirror/

CMD ["python", "-m", "prediction_mirror", "run"]
