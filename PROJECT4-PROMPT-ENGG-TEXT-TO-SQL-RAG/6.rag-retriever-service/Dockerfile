FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app
COPY 6.rag-retriever-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared ./shared
COPY 6.rag-retriever-service ./6.rag-retriever-service

EXPOSE 8080
CMD ["uvicorn", "app:app", "--app-dir", "/app/6.rag-retriever-service", "--host", "0.0.0.0", "--port", "8080"]
