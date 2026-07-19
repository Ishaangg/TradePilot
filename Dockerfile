FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY compliance_agent ./compliance_agent
COPY freight_agent ./freight_agent
COPY data ./data
COPY prompts ./prompts

EXPOSE 8000 8001 8002

