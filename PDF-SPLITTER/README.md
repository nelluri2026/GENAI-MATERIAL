# PDF to Pinecone RAG MVP

This is a small, practical MVP for ingesting a mixed-content PDF into Pinecone using OpenAI embeddings, then asking questions with an OpenAI LLM.

The pipeline is:

```text
PDF -> text/table extraction -> recursive chunking -> OpenAI embeddings -> Pinecone -> RAG answer
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and add your OpenAI and Pinecone keys.

## Inspect the Sample PDF

This does extraction and chunking only. It does not call OpenAI or Pinecone.

```bash
python rag_mvp.py inspect "Sample Postgresql Best Practices Document.pdf"
```

## Ingest into Pinecone

This creates the Pinecone index if it does not already exist, embeds chunks, and upserts them.

```bash
python rag_mvp.py ingest "Sample Postgresql Best Practices Document.pdf"
```

## Ask a Question

```bash
python rag_mvp.py ask "What are the PostgreSQL backup best practices?"
```

## Notes

- `pdfplumber` is used first because it can extract both text and tables.
- `pypdf` is used as a fallback for text-only extraction.
- `RecursiveCharacterTextSplitter` is used when `langchain-text-splitters` is installed.
- Every chunk stores page number, content type, source file, and chunk index as Pinecone metadata.
- For scanned PDFs, add an OCR step later using Tesseract, AWS Textract, Azure Document Intelligence, Google Document AI, or OpenAI vision-based extraction.
