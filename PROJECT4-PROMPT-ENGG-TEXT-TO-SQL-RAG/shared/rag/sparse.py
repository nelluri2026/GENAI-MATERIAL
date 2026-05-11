import hashlib
import math
import re

TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text)]


def stable_sparse_index(token: str, dimensions: int = 100_000) -> int:
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    return int(digest[:12], 16) % dimensions


def build_sparse_vector(text: str) -> dict[str, list[int] | list[float]]:
    """Build a deterministic sparse vector suitable for Pinecone hybrid search."""
    counts: dict[int, int] = {}
    for token in tokenize(text):
        idx = stable_sparse_index(token)
        counts[idx] = counts.get(idx, 0) + 1

    if not counts:
        return {"indices": [], "values": []}

    indices = sorted(counts)
    values = [1.0 + math.log(counts[index]) for index in indices]
    return {"indices": indices, "values": values}

