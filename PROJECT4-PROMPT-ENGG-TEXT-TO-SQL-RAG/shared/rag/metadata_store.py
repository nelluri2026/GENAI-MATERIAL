from datetime import datetime, timezone
from typing import Any

import boto3

from shared.rag.secrets import get_config_value


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RagMetadataStore:
    """Optional DynamoDB-backed version registry for RAG documents."""

    def __init__(self) -> None:
        self.table_name = get_config_value("RAG_METADATA_TABLE")
        self.table = None
        if self.table_name:
            self.table = boto3.resource("dynamodb").Table(self.table_name)

    @property
    def enabled(self) -> bool:
        return self.table is not None

    def get_active_version(self, doc_id: str) -> dict[str, Any] | None:
        if not self.table:
            return None
        response = self.table.get_item(Key={"doc_id": doc_id, "version_status": "ACTIVE"})
        return response.get("Item")

    def mark_processing(self, document_metadata: dict[str, Any]) -> None:
        if not self.table:
            return
        self.table.put_item(
            Item={
                "doc_id": document_metadata["doc_id"],
                "version_status": f"VERSION#{document_metadata['doc_version']}",
                "doc_version": document_metadata["doc_version"],
                "checksum": document_metadata["checksum"],
                "status": "PROCESSING",
                "doc_path": document_metadata.get("doc_path", ""),
                "source_uri": document_metadata.get("source_uri", ""),
                "updated_at": utc_now(),
            }
        )

    def mark_active(self, document_metadata: dict[str, Any], chunk_count: int) -> None:
        if not self.table:
            return
        active_item = {
            "doc_id": document_metadata["doc_id"],
            "version_status": "ACTIVE",
            "doc_version": document_metadata["doc_version"],
            "checksum": document_metadata["checksum"],
            "status": "ACTIVE",
            "chunk_count": chunk_count,
            "doc_path": document_metadata.get("doc_path", ""),
            "source_uri": document_metadata.get("source_uri", ""),
            "updated_at": utc_now(),
        }
        version_item = {**active_item, "version_status": f"VERSION#{document_metadata['doc_version']}"}
        self.table.put_item(Item=active_item)
        self.table.put_item(Item=version_item)

    def mark_failed(self, document_metadata: dict[str, Any], error: str) -> None:
        if not self.table:
            return
        self.table.put_item(
            Item={
                "doc_id": document_metadata["doc_id"],
                "version_status": f"VERSION#{document_metadata['doc_version']}",
                "doc_version": document_metadata["doc_version"],
                "checksum": document_metadata["checksum"],
                "status": "FAILED",
                "error": error[:1000],
                "updated_at": utc_now(),
            }
        )

