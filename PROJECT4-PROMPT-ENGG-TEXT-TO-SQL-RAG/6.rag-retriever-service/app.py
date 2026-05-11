import logging
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from shared.rag.embeddings import OpenAIEmbeddingClient
from shared.rag.pinecone_store import PineconeRagStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rag-retriever-service")

app = FastAPI(title="RAG Retriever Service", version="1.0.0")


class RetrieveRequest(BaseModel):
    query: str
    top_k: int = Field(default=6, ge=1, le=20)
    alpha: float = Field(default=0.6, ge=0.0, le=1.0)
    metadata_filter: dict[str, Any] | None = None


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/retrieve")
def retrieve(request: RetrieveRequest) -> dict[str, Any]:
    embedder = OpenAIEmbeddingClient()
    store = PineconeRagStore()
    dense_vector = embedder.embed_query(request.query)
    matches = store.search(
        query=request.query,
        dense_vector=dense_vector,
        top_k=request.top_k,
        alpha=request.alpha,
        metadata_filter=request.metadata_filter,
    )
    logger.info("Retrieved %s matches for query=%s", len(matches), request.query)
    return {"matches": matches, "namespace": store.namespace}

