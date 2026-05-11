FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY rag-docs ./rag-docs
COPY 4.rag-document-publisher ./4.rag-document-publisher

ENTRYPOINT ["python", "4.rag-document-publisher/publish_to_s3.py"]

