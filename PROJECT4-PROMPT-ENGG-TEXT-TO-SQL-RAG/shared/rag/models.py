from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RagDocument:
    doc_id: str
    source_uri: str
    text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class RagChunk:
    id: str
    doc_id: str
    text: str
    metadata: dict[str, Any]

