FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY logsentinel.py .
COPY config.yaml .

RUN chmod +x logsentinel.py

# For docker socket access
RUN groupadd -r logsentinel && useradd -r -g logsentinel logsentinel

ENTRYPOINT ["python3", "logsentinel.py"]
