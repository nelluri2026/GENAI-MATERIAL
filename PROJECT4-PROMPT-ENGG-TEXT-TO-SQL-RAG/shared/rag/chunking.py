from langchain_text_splitters import MarkdownHeaderTextSplitter, RecursiveCharacterTextSplitter

from shared.rag.models import RagChunk, RagDocument


def chunk_document(document: RagDocument, chunk_size: int = 900, chunk_overlap: int = 120) -> list[RagChunk]:
    """Split markdown-aware documents into stable, metadata-rich chunks."""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=[
            ("#", "h1"),
            ("##", "h2"),
            ("###", "h3"),
        ],
        strip_headers=False,
    )
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    header_docs = header_splitter.split_text(document.text)
    chunks: list[RagChunk] = []
    for header_doc in header_docs:
        pieces = text_splitter.split_text(header_doc.page_content)
        for piece in pieces:
            chunk_index = len(chunks)
            chunk_id = f"{document.doc_id}::{document.metadata['doc_version']}::chunk-{chunk_index:04d}"
            metadata = {
                **document.metadata,
                **header_doc.metadata,
                "chunk_index": chunk_index,
                "text": piece,
            }
            chunks.append(RagChunk(id=chunk_id, doc_id=document.doc_id, text=piece, metadata=metadata))
    return chunks

