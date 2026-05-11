import hashlib
import os
from pathlib import Path
from typing import Any

import boto3

from shared.rag.frontmatter import FRONTMATTER_PATTERN, parse_simple_yaml
from shared.rag.models import RagDocument

def parse_markdown_document(text: str) -> tuple[dict[str, Any], str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}, text
    metadata = parse_simple_yaml(match.group(1))
    return metadata, match.group(2)


def checksum_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_local_documents(root: str) -> list[RagDocument]:
    base = Path(root)
    documents: list[RagDocument] = []
    for path in sorted(base.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        frontmatter, body = parse_markdown_document(raw)
        relative_path = path.relative_to(base).as_posix()
        version = os.environ.get("GIT_COMMIT_SHA") or checksum_text(raw)[:16]
        doc_id = frontmatter.get("doc_id", relative_path)
        metadata = {
            **frontmatter,
            "doc_id": doc_id,
            "doc_path": relative_path,
            "doc_version": version,
            "checksum": checksum_text(raw),
            "source_type": "git",
            "status": frontmatter.get("status", "active"),
        }
        documents.append(RagDocument(doc_id=doc_id, source_uri=str(path), text=body, metadata=metadata))
    return documents


def load_s3_document(bucket: str, key: str, version_id: str | None = None) -> RagDocument:
    client = boto3.client("s3")
    kwargs: dict[str, Any] = {"Bucket": bucket, "Key": key}
    if version_id:
        kwargs["VersionId"] = version_id
    response = client.get_object(**kwargs)
    raw = response["Body"].read().decode("utf-8")
    frontmatter, body = parse_markdown_document(raw)
    s3_version_id = response.get("VersionId") or version_id or checksum_text(raw)[:16]
    metadata = {
        **frontmatter,
        "doc_id": frontmatter.get("doc_id", key),
        "doc_path": key,
        "doc_version": s3_version_id,
        "s3_bucket": bucket,
        "s3_key": key,
        "s3_version_id": s3_version_id,
        "checksum": checksum_text(raw),
        "source_type": "s3",
        "source_uri": f"s3://{bucket}/{key}",
        "status": frontmatter.get("status", "active"),
    }
    return RagDocument(doc_id=metadata["doc_id"], source_uri=metadata["source_uri"], text=body, metadata=metadata)
