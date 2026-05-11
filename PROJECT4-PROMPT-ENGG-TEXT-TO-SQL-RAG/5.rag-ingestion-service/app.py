import json
import logging
import os
from typing import Any
from urllib.parse import unquote_plus

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from shared.rag.chunking import chunk_document
from shared.rag.documents import load_local_documents, load_s3_document
from shared.rag.embeddings import OpenAIEmbeddingClient
from shared.rag.metadata_store import RagMetadataStore
from shared.rag.pinecone_store import PineconeRagStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-ingestion-service")

app = FastAPI(title="RAG Ingestion Service", version="1.0.0")


class IngestLocalRequest(BaseModel):
    doc_root: str = "rag-docs"


class IngestS3Request(BaseModel):
    bucket: str
    key: str
    version_id: str | None = None


def ingest_document(document) -> dict[str, Any]:
    chunk_size = int(os.environ.get("RAG_CHUNK_SIZE", "900"))
    chunk_overlap = int(os.environ.get("RAG_CHUNK_OVERLAP", "120"))
    metadata_store = RagMetadataStore()
    active_version = metadata_store.get_active_version(document.doc_id)
    if active_version and active_version.get("checksum") == document.metadata["checksum"]:
        return {
            "doc_id": document.doc_id,
            "doc_version": active_version["doc_version"],
            "chunk_count": active_version.get("chunk_count", 0),
            "skipped": True,
            "reason": "checksum unchanged",
        }

    metadata_store.mark_processing(document.metadata)
    chunks = chunk_document(document, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    embedder = OpenAIEmbeddingClient()
    store = PineconeRagStore()
    try:
        dense_vectors = embedder.embed_texts([chunk.text for chunk in chunks])
        store.upsert_chunks(chunks, dense_vectors)
        if active_version and os.environ.get("RAG_DELETE_OLD_VECTORS", "true").lower() == "true":
            store.delete_document_version(document.doc_id, active_version["doc_version"])
        metadata_store.mark_active(document.metadata, len(chunks))
        logger.info("Ingested document %s version %s chunks=%s", document.doc_id, document.metadata["doc_version"], len(chunks))
        return {
            "doc_id": document.doc_id,
            "doc_version": document.metadata["doc_version"],
            "chunk_count": len(chunks),
            "namespace": store.namespace,
            "skipped": False,
        }
    except Exception as exc:
        metadata_store.mark_failed(document.metadata, str(exc))
        raise


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/ingest/local")
def ingest_local(request: IngestLocalRequest) -> dict[str, Any]:
    documents = load_local_documents(request.doc_root)
    return {"documents": [ingest_document(document) for document in documents]}


@app.post("/ingest/s3")
def ingest_s3(request: IngestS3Request) -> dict[str, Any]:
    try:
        document = load_s3_document(request.bucket, request.key, request.version_id)
        return ingest_document(document)
    except Exception as exc:
        logger.exception("S3 ingestion failed")
        raise HTTPException(status_code=500, detail=str(exc)) from exc


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Support direct S3 EventBridge/Lambda ingestion."""
    logger.info("Received event: %s", json.dumps(event))
    records = event.get("Records", [])
    results = []
    for record in records:
        bucket = record["s3"]["bucket"]["name"]
        key = unquote_plus(record["s3"]["object"]["key"])
        if not key.endswith(".md"):
            continue
        version_id = record["s3"]["object"].get("versionId")
        document = load_s3_document(bucket, key, version_id)
        results.append(ingest_document(document))
    return {"statusCode": 200, "body": json.dumps({"documents": results})}
