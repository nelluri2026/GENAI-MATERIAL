from __future__ import annotations

import argparse
import hashlib
import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from dotenv import load_dotenv
from openai import OpenAI


DEFAULT_PDF = "Sample Postgresql Best Practices Document.pdf"


@dataclass
class ExtractedBlock:
    text: str
    metadata: dict


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"{name} must be an integer, got {value!r}")


def table_to_markdown(table: list[list[object]]) -> str:
    rows = [["" if cell is None else str(cell).strip() for cell in row] for row in table if row]
    rows = [row for row in rows if any(cell for cell in row)]
    if not rows:
        return ""

    max_cols = max(len(row) for row in rows)
    normalized = [row + [""] * (max_cols - len(row)) for row in rows]
    header = normalized[0]
    body = normalized[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(["---"] * max_cols) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def extract_with_pdfplumber(pdf_path: Path) -> list[ExtractedBlock]:
    import pdfplumber

    blocks: list[ExtractedBlock] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        doc_metadata = dict(pdf.metadata or {})
        total_pages = len(pdf.pages)

        for page_number, page in enumerate(pdf.pages, start=1):
            base_metadata = {
                "source": pdf_path.name,
                "page": page_number,
                "total_pages": total_pages,
                "extractor": "pdfplumber",
            }

            text = (page.extract_text(x_tolerance=1, y_tolerance=3) or "").strip()
            if text:
                blocks.append(
                    ExtractedBlock(
                        text=text,
                        metadata={**base_metadata, "content_type": "text"},
                    )
                )

            for table_index, table in enumerate(page.extract_tables() or [], start=1):
                markdown = table_to_markdown(table)
                if markdown:
                    blocks.append(
                        ExtractedBlock(
                            text=markdown,
                            metadata={
                                **base_metadata,
                                "content_type": "table",
                                "table_index": table_index,
                            },
                        )
                    )

        if doc_metadata:
            metadata_text = "\n".join(f"{key}: {value}" for key, value in doc_metadata.items())
            blocks.append(
                ExtractedBlock(
                    text=metadata_text,
                    metadata={
                        "source": pdf_path.name,
                        "page": 0,
                        "total_pages": total_pages,
                        "extractor": "pdfplumber",
                        "content_type": "metadata",
                    },
                )
            )

    return blocks


def extract_with_pypdf(pdf_path: Path) -> list[ExtractedBlock]:
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    total_pages = len(reader.pages)
    blocks: list[ExtractedBlock] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            blocks.append(
                ExtractedBlock(
                    text=text,
                    metadata={
                        "source": pdf_path.name,
                        "page": page_number,
                        "total_pages": total_pages,
                        "extractor": "pypdf",
                        "content_type": "text",
                    },
                )
            )

    if reader.metadata:
        metadata_text = "\n".join(f"{key}: {value}" for key, value in dict(reader.metadata).items())
        blocks.append(
            ExtractedBlock(
                text=metadata_text,
                metadata={
                    "source": pdf_path.name,
                    "page": 0,
                    "total_pages": total_pages,
                    "extractor": "pypdf",
                    "content_type": "metadata",
                },
            )
        )

    return blocks


def extract_pdf(pdf_path: Path) -> list[ExtractedBlock]:
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found: {pdf_path}")

    try:
        return extract_with_pdfplumber(pdf_path)
    except ImportError:
        print("pdfplumber is not installed; falling back to pypdf.", file=sys.stderr)
    except Exception as exc:
        print(f"pdfplumber extraction failed: {exc}. Falling back to pypdf.", file=sys.stderr)

    try:
        return extract_with_pypdf(pdf_path)
    except ImportError:
        raise SystemExit("Install PDF dependencies first: pip install -r requirements.txt")


class SimpleRecursiveTextSplitter:
    def __init__(self, chunk_size: int, chunk_overlap: int, separators: list[str]) -> None:
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.separators = separators

    def split_text(self, text: str) -> list[str]:
        pieces = self._split(text, self.separators)
        chunks: list[str] = []
        current = ""

        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            candidate = f"{current}\n{piece}".strip() if current else piece
            if len(candidate) <= self.chunk_size:
                current = candidate
            else:
                if current:
                    chunks.append(current)
                current = piece

        if current:
            chunks.append(current)

        if self.chunk_overlap <= 0 or len(chunks) <= 1:
            return chunks

        overlapped: list[str] = []
        previous_tail = ""
        for chunk in chunks:
            with_overlap = f"{previous_tail}\n{chunk}".strip() if previous_tail else chunk
            overlapped.append(with_overlap)
            previous_tail = chunk[-self.chunk_overlap :]
        return overlapped

    def _split(self, text: str, separators: list[str]) -> list[str]:
        if len(text) <= self.chunk_size:
            return [text]
        if not separators:
            return [text[i : i + self.chunk_size] for i in range(0, len(text), self.chunk_size)]

        separator = separators[0]
        if separator and separator in text:
            pieces = text.split(separator)
        elif separator == "":
            pieces = list(text)
        else:
            return self._split(text, separators[1:])

        output: list[str] = []
        for piece in pieces:
            if len(piece) > self.chunk_size:
                output.extend(self._split(piece, separators[1:]))
            else:
                output.append(piece)
        return output


def make_splitter(chunk_size: int, chunk_overlap: int):
    separators = ["\n\n", "\n", ". ", " ", ""]
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        return RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=separators,
            length_function=len,
        )
    except ImportError:
        print("langchain-text-splitters is not installed; using local fallback splitter.", file=sys.stderr)
        return SimpleRecursiveTextSplitter(chunk_size, chunk_overlap, separators)


def stable_chunk_id(source: str, page: int, content_type: str, chunk_index: int, text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    raw = f"{source}:{page}:{content_type}:{chunk_index}:{digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def chunk_blocks(blocks: list[ExtractedBlock], chunk_size: int, chunk_overlap: int) -> list[Chunk]:
    splitter = make_splitter(chunk_size, chunk_overlap)
    chunks: list[Chunk] = []

    for block in blocks:
        split_texts = splitter.split_text(block.text)
        for local_index, text in enumerate(split_texts):
            text = text.strip()
            if not text:
                continue
            metadata = {
                **block.metadata,
                "chunk_index": local_index,
                "text": text,
            }
            chunks.append(
                Chunk(
                    id=stable_chunk_id(
                        source=str(block.metadata.get("source", "unknown")),
                        page=int(block.metadata.get("page", 0)),
                        content_type=str(block.metadata.get("content_type", "text")),
                        chunk_index=local_index,
                        text=text,
                    ),
                    text=text,
                    metadata=metadata,
                )
            )

    return chunks


def batched(items: list, size: int) -> Iterable[list]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def embed_texts(client: OpenAI, texts: list[str], model: str, dimensions: int) -> list[list[float]]:
    vectors: list[list[float]] = []
    for batch in batched(texts, 64):
        response = client.embeddings.create(
            model=model,
            input=batch,
            dimensions=dimensions,
            encoding_format="float",
        )
        vectors.extend(item.embedding for item in response.data)
    return vectors


def get_pinecone_index(index_name: str, dimension: int, create_if_missing: bool):
    from pinecone import Pinecone, ServerlessSpec

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise SystemExit("Missing PINECONE_API_KEY. Add it to .env or your shell environment.")

    pc = Pinecone(api_key=api_key)
    existing_names = {index.name for index in pc.list_indexes()}

    if index_name not in existing_names:
        if not create_if_missing:
            raise SystemExit(f"Pinecone index {index_name!r} does not exist.")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(
                cloud=os.getenv("PINECONE_CLOUD", "aws"),
                region=os.getenv("PINECONE_REGION", "us-east-1"),
            ),
        )
        while not pc.describe_index(index_name).status["ready"]:
            time.sleep(2)

    return pc.Index(index_name)


def ingest(args: argparse.Namespace) -> None:
    load_dotenv()
    pdf_path = Path(args.pdf)
    chunk_size = env_int("CHUNK_SIZE", 800)
    chunk_overlap = env_int("CHUNK_OVERLAP", 120)
    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions = env_int("OPENAI_EMBEDDING_DIMENSIONS", 1536)
    index_name = os.getenv("PINECONE_INDEX", "pdf-rag-mvp")
    namespace = os.getenv("PINECONE_NAMESPACE", "default")

    blocks = extract_pdf(pdf_path)
    chunks = chunk_blocks(blocks, chunk_size, chunk_overlap)
    if not chunks:
        raise SystemExit("No extractable text found. This PDF may need OCR/image extraction.")

    print(f"Extracted {len(blocks)} blocks and created {len(chunks)} chunks.")

    client = OpenAI()
    index = get_pinecone_index(index_name, dimensions, create_if_missing=True)

    for chunk_batch in batched(chunks, 64):
        vectors = embed_texts(client, [chunk.text for chunk in chunk_batch], embedding_model, dimensions)
        records = [
            {
                "id": chunk.id,
                "values": vector,
                "metadata": chunk.metadata,
            }
            for chunk, vector in zip(chunk_batch, vectors)
        ]
        index.upsert(vectors=records, namespace=namespace)

    print(f"Upserted {len(chunks)} chunks to Pinecone index {index_name!r}, namespace {namespace!r}.")


def inspect_pdf(args: argparse.Namespace) -> None:
    load_dotenv()
    pdf_path = Path(args.pdf)
    chunk_size = env_int("CHUNK_SIZE", 800)
    chunk_overlap = env_int("CHUNK_OVERLAP", 120)

    blocks = extract_pdf(pdf_path)
    chunks = chunk_blocks(blocks, chunk_size, chunk_overlap)
    content_types: dict[str, int] = {}
    for block in blocks:
        content_type = str(block.metadata.get("content_type", "unknown"))
        content_types[content_type] = content_types.get(content_type, 0) + 1

    print(f"PDF: {pdf_path.name}")
    print(f"Blocks: {len(blocks)}")
    print(f"Chunks: {len(chunks)}")
    print(f"Content types: {content_types}")
    print()

    for chunk in chunks[: args.preview_chunks]:
        page = chunk.metadata.get("page")
        content_type = chunk.metadata.get("content_type")
        print(f"--- chunk {chunk.metadata['chunk_index']} | page={page} | type={content_type} ---")
        print(chunk.text[:700])
        print()


def response_text(response) -> str:
    text = getattr(response, "output_text", None)
    if text:
        return text

    pieces: list[str] = []
    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            value = getattr(content, "text", None)
            if value:
                pieces.append(value)
    return "\n".join(pieces).strip()


def ask(args: argparse.Namespace) -> None:
    load_dotenv()
    embedding_model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    dimensions = env_int("OPENAI_EMBEDDING_DIMENSIONS", 1536)
    llm_model = os.getenv("OPENAI_LLM_MODEL", "gpt-5-mini")
    index_name = os.getenv("PINECONE_INDEX", "pdf-rag-mvp")
    namespace = os.getenv("PINECONE_NAMESPACE", "default")

    client = OpenAI()
    index = get_pinecone_index(index_name, dimensions, create_if_missing=False)
    query_vector = embed_texts(client, [args.question], embedding_model, dimensions)[0]

    result = index.query(
        vector=query_vector,
        top_k=args.top_k,
        namespace=namespace,
        include_metadata=True,
    )

    matches = result.get("matches", []) if isinstance(result, dict) else result.matches
    if not matches:
        raise SystemExit("No matches found in Pinecone. Run ingest first.")

    context_blocks = []
    sources = []
    for i, match in enumerate(matches, start=1):
        metadata = match.get("metadata", {}) if isinstance(match, dict) else match.metadata
        score = match.get("score") if isinstance(match, dict) else match.score
        text = metadata.get("text", "")
        source = metadata.get("source", "unknown")
        page = metadata.get("page", "?")
        content_type = metadata.get("content_type", "text")
        sources.append(f"[{i}] {source}, page {page}, {content_type}, score={score:.4f}")
        context_blocks.append(f"[{i}] Source: {source}, page {page}, type {content_type}\n{text}")

    prompt = f"""Answer the user's question using only the context below.
If the context is not enough, say what is missing.
Cite sources inline like [1] or [2].

Question:
{args.question}

Context:
{chr(10).join(context_blocks)}
"""

    response = client.responses.create(
        model=llm_model,
        input=[
            {
                "role": "system",
                "content": "You are a careful RAG assistant. Ground answers in provided context and cite sources.",
            },
            {"role": "user", "content": prompt},
        ],
    )

    print(response_text(response))
    print("\nSources:")
    for source in sources:
        print(source)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="PDF to Pinecone RAG MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    inspect_parser = subparsers.add_parser("inspect", help="Extract and preview chunks without API calls")
    inspect_parser.add_argument("pdf", nargs="?", default=DEFAULT_PDF)
    inspect_parser.add_argument("--preview-chunks", type=int, default=5)
    inspect_parser.set_defaults(func=inspect_pdf)

    ingest_parser = subparsers.add_parser("ingest", help="Embed chunks and upsert them to Pinecone")
    ingest_parser.add_argument("pdf", nargs="?", default=DEFAULT_PDF)
    ingest_parser.set_defaults(func=ingest)

    ask_parser = subparsers.add_parser("ask", help="Ask a question against the Pinecone index")
    ask_parser.add_argument("question")
    ask_parser.add_argument("--top-k", type=int, default=5)
    ask_parser.set_defaults(func=ask)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
