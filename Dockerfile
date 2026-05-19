FROM python:3.11-slim

WORKDIR /app

# Install kubectl for Kubernetes log streaming
RUN apt-get update && apt-get install -y curl \
    && curl -LO "https://dl.k8s.io/release/v1.28.0/bin/linux/amd64/kubectl" \
    && chmod +x kubectl \
    && mv kubectl /usr/local/bin/ \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY logsentinel.py .
COPY config.yaml .
COPY collectors/ collectors/
COPY output/ output/
COPY tests/ tests/

RUN chmod +x logsentinel.py

# For docker socket access
RUN groupadd -r logsentinel && useradd -r -g logsentinel logsentinel

ENTRYPOINT ["python3", "logsentinel.py"]
