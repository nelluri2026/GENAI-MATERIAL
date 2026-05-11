from typing import Any

from pinecone import Pinecone

from shared.rag.models import RagChunk
from shared.rag.secrets import get_config_value
from shared.rag.sparse import build_sparse_vector


class PineconeRagStore:
    def __init__(self) -> None:
        api_key = get_config_value("PINECONE_API_KEY")
        index_name = get_config_value("PINECONE_INDEX_NAME")
        if not api_key or not index_name:
            raise ValueError("PINECONE_API_KEY and PINECONE_INDEX_NAME are required")
        self.namespace = get_config_value("PINECONE_NAMESPACE", "business-docs-dev")
        self.pc = Pinecone(api_key=api_key)
        self.index = self.pc.Index(index_name)

    def upsert_chunks(self, chunks: list[RagChunk], dense_vectors: list[list[float]]) -> None:
        vectors: list[dict[str, Any]] = []
        for chunk, dense_vector in zip(chunks, dense_vectors, strict=True):
            vectors.append(
                {
                    "id": chunk.id,
                    "values": dense_vector,
                    "sparse_values": build_sparse_vector(chunk.text),
                    "metadata": chunk.metadata,
                }
            )
        if vectors:
            self.index.upsert(vectors=vectors, namespace=self.namespace)

    def search(
        self,
        query: str,
        dense_vector: list[float],
        top_k: int = 6,
        alpha: float = 0.6,
        metadata_filter: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        sparse_vector = build_sparse_vector(query)
        scaled_dense = [value * alpha for value in dense_vector]
        sparse_values = {
            "indices": sparse_vector["indices"],
            "values": [value * (1.0 - alpha) for value in sparse_vector["values"]],
        }
        response = self.index.query(
            namespace=self.namespace,
            vector=scaled_dense,
            sparse_vector=sparse_values,
            top_k=top_k,
            include_metadata=True,
            filter=metadata_filter or {"status": {"$eq": "active"}},
        )
        matches = response.get("matches", []) if isinstance(response, dict) else getattr(response, "matches", [])
        return [
            {
                "id": match["id"] if isinstance(match, dict) else match.id,
                "score": match["score"] if isinstance(match, dict) else match.score,
                "metadata": match.get("metadata", {}) if isinstance(match, dict) else (match.metadata or {}),
                "text": (match.get("metadata", {}) if isinstance(match, dict) else (match.metadata or {})).get("text", ""),
            }
            for match in matches
        ]

    def delete_document_version(self, doc_id: str, doc_version: str) -> None:
        self.index.delete(
            namespace=self.namespace,
            filter={"doc_id": {"$eq": doc_id}, "doc_version": {"$eq": doc_version}},
        )
