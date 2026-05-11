# Production RAG Text-to-SQL Assistant

This project is a production-shaped hands-on system for teaching **Text-to-SQL + RAG** with AWS, OpenAI, Pinecone, S3, GitHub Actions, and Python microservices.

Users ask natural language questions. The system retrieves relevant schema/business context from Pinecone, generates safe SQL, executes it on PostgreSQL, and returns a business-friendly answer.

## Architecture

```text
Chainlit UI
  -> LLM Text-to-SQL Agent
     -> RAG Retriever Service
        -> Pinecone hybrid index
     -> Generic Query Executor
        -> PostgreSQL demo.customers + demo.orders

GitHub rag-docs/
  -> GitHub Actions validation
  -> Publish docs to S3
  -> S3 event triggers RAG Ingestion Lambda
  -> OpenAI embeddings + sparse vectors
  -> Pinecone upsert
```

## Services

| Path | Purpose | Deploy As |
|---|---|---|
| `1.generic-query-executor/` | Executes SQL against PostgreSQL using Secrets Manager credentials | Lambda container |
| `2.llm-text-sql-agent/` | Orchestrates intent, RAG retrieval, SQL generation, validation, execution, and formatting | Lambda container |
| `3.chat-assistant/` | Chainlit chat UI | ECS/EKS container |
| `4.rag-document-publisher/` | Validates and publishes reviewed RAG docs from Git to S3 | GitHub Actions job or container |
| `5.rag-ingestion-service/` | Chunks docs, embeds, creates sparse vectors, upserts to Pinecone | ECS/EKS service or S3-triggered Lambda |
| `6.rag-retriever-service/` | Hybrid dense+sparse retrieval from Pinecone | ECS/EKS service |
| `shared/rag/` | Shared secrets, document parsing, chunking, embeddings, sparse vectors, Pinecone store | Python library copied into services |

## RAG Design

The vector database is **not** the source of truth. It is a serving index.

```text
Git = reviewed authoring source
S3 = versioned published document lake
Pinecone = derived vector/sparse index
LLM agent = runtime consumer
```

RAG retrieves database knowledge, not transactional data:

- schema documentation
- relationships
- business rules
- metric definitions
- glossary terms
- few-shot SQL examples

Actual customer/order data is still retrieved through SQL.

## Document Corpus

RAG docs live in `rag-docs/`.

Each markdown file requires YAML frontmatter:

```yaml
---
doc_id: rule_revenue_definitions
doc_type: business_rule
domain: orders
owner: finance
status: active
---
```

Current sample docs:

- `rag-docs/schema/customers.md`
- `rag-docs/schema/orders.md`
- `rag-docs/schema/relationships.md`
- `rag-docs/business-rules/revenue_definitions.md`
- `rag-docs/business-rules/customer_metrics.md`
- `rag-docs/business-rules/order_status_definitions.md`
- `rag-docs/examples/analytics_examples.md`
- `rag-docs/glossary/sql_terms.md`

## Vector Metadata

Each Pinecone chunk includes metadata similar to:

```json
{
  "doc_id": "rule_revenue_definitions",
  "doc_path": "business-rules/revenue_definitions.md",
  "doc_version": "git_sha_or_s3_version_id",
  "checksum": "sha256",
  "doc_type": "business_rule",
  "domain": "orders",
  "owner": "finance",
  "status": "active",
  "chunk_index": 0,
  "text": "chunk text"
}
```

Chunk IDs are deterministic:

```text
{doc_id}::{doc_version}::chunk-0000
```

## AWS Secrets

Create these secrets in AWS Secrets Manager.

### `rag-platform-secrets`

```json
{
  "OPENAI_API_KEY": "sk-...",
  "OPENAI_EMBEDDING_MODEL": "text-embedding-3-small",
  "PINECONE_API_KEY": "...",
  "PINECONE_INDEX_NAME": "text-to-sql-rag",
  "PINECONE_NAMESPACE": "business-docs-prod",
  "RAG_METADATA_TABLE": "rag-document-versions"
}
```

### `llm-text-sql-agent-secrets`

```json
{
  "OPENAI_API_KEY": "sk-...",
  "OPENAI_MODEL": "gpt-4o-mini",
  "QUERY_EXECUTOR_FUNCTION": "generic-query-executor"
}
```

### `postgres`

```json
{
  "host": "your-rds-endpoint",
  "dbname": "postgres",
  "username": "postgres",
  "password": "postgres1234",
  "port": "5432"
}
```

## Environment Variables

Start from `.env.example`.

Important runtime variables:

```bash
RAG_SECRET_NAME=rag-platform-secrets
SECRET_NAME=llm-text-sql-agent-secrets
DB_SECRET_NAME=postgres
RAG_RETRIEVER_URL=http://rag-retriever-service:8080
RAG_TOP_K=6
RAG_ALPHA=0.6
ENABLE_RAG_DEBUG=true
ALLOW_WRITE_SQL=false
RAG_METADATA_TABLE=rag-document-versions
RAG_DELETE_OLD_VECTORS=true
```

`ALLOW_WRITE_SQL=false` keeps the assistant read-only by default.

## Version Registry

For production, create a DynamoDB table:

```text
Table name: rag-document-versions
Partition key: doc_id
Sort key: version_status
```

The ingestion service writes:

- `version_status=ACTIVE` for the currently active document version
- `version_status=VERSION#{doc_version}` for each processed version

If a document checksum is unchanged, ingestion is skipped. If a document changes, new chunks are inserted and old active chunks are deleted when `RAG_DELETE_OLD_VECTORS=true`.

## Local Hands-On

Create `.env`:

```bash
cp .env.example .env
```

Start PostgreSQL and pgAdmin:

```bash
docker compose up -d postgres pgadmin
```

Start RAG services:

```bash
docker compose --profile rag up --build
```

Ingest local docs through the ingestion service:

```bash
curl -X POST http://localhost:8081/ingest/local \
  -H "Content-Type: application/json" \
  -d '{"doc_root":"rag-docs"}'
```

Test retrieval:

```bash
curl -X POST http://localhost:8082/retrieve \
  -H "Content-Type: application/json" \
  -d '{"query":"revenue by city excluding cancelled orders","top_k":5,"alpha":0.6}'
```

## PostgreSQL Setup

Use `docker-compose.yml` for local PostgreSQL or RDS for AWS.

Create schema:

```sql
CREATE SCHEMA IF NOT EXISTS demo;

CREATE TABLE demo.customers (
    customer_id VARCHAR(20) PRIMARY KEY,
    customer_name VARCHAR(100),
    email VARCHAR(150),
    city VARCHAR(50),
    state VARCHAR(10),
    created_at TIMESTAMP
);

CREATE TABLE demo.orders (
    order_id VARCHAR(20) PRIMARY KEY,
    customer_id VARCHAR(20),
    order_date TIMESTAMP,
    status VARCHAR(50),
    total_amount NUMERIC(10,2),
    FOREIGN KEY (customer_id) REFERENCES demo.customers(customer_id)
);
```

Load:

- `post-gres-files/customers.csv`
- `post-gres-files/orders.csv`

## Pinecone Setup

Create a Pinecone index for OpenAI `text-embedding-3-small`.

Recommended:

```text
Index name: text-to-sql-rag
Dimension: 1536
Metric: dotproduct
```

This project upserts both:

- dense OpenAI embeddings
- deterministic sparse vectors for hybrid search

`RAG_ALPHA` controls hybrid weighting:

```text
1.0 = dense only
0.0 = sparse only
0.6 = balanced hybrid default
```

## GitOps Document Flow

Production document flow:

```text
Pull request changes rag-docs/
  -> validate frontmatter
  -> merge to main
  -> GitHub Actions uploads docs to S3
  -> S3 ObjectCreated event invokes ingestion Lambda
  -> ingestion chunks + embeds + upserts to Pinecone
```

GitHub workflow:

- `.github/workflows/rag-docs-gitops.yml`

Required GitHub variables:

```text
AWS_REGION
RAG_DOCS_BUCKET
RAG_DOCS_PREFIX
```

Required GitHub secret:

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

The S3 bucket should have versioning enabled.

## S3 Triggered Ingestion

Build and deploy the Lambda image from:

```text
5.rag-ingestion-service/Dockerfile.lambda
```

Configure S3 event notification:

```text
Event: s3:ObjectCreated:*
Prefix: business-docs/
Suffix: .md
Destination: rag-ingestion-lambda
```

The Lambda uses the same code as the HTTP ingestion service.

## ECR Build CI/CD

Image workflow:

- `.github/workflows/build-images.yml`

It builds and pushes:

- `generic-query-executor`
- `llm-text-sql-agent`
- `chat-assistant`
- `rag-document-publisher`
- `rag-ingestion-service`
- `rag-ingestion-lambda`
- `rag-retriever-service`

Required GitHub variables:

```text
AWS_ACCOUNT_ID
AWS_REGION
```

Required GitHub secret:

```text
AWS_GITHUB_ACTIONS_ROLE_ARN
```

## LLM Agent RAG Behavior

`2.llm-text-sql-agent/lambda_function.py` now:

1. Detects intent.
2. Calls `RAG_RETRIEVER_URL/retrieve`.
3. Adds retrieved context to the SQL generation prompt.
4. Validates SQL.
5. Invokes `generic-query-executor`.
6. Formats the business answer.
7. Optionally returns retrieved chunks when `ENABLE_RAG_DEBUG=true`.

If `RAG_RETRIEVER_URL` is not set, the agent falls back to the static schema prompt.

## Kubernetes/EKS Starting Point

Use:

```text
deployment/kubernetes-rag-services.yaml
```

Replace:

```text
ACCOUNT_ID
REGION
TAG
```

For ECS, deploy the same images as services and pass the same environment variables.

## Production Recommendations

Use this as the teaching production standard:

- Keep RAG docs in Git with pull request review.
- Publish approved docs to versioned S3.
- Treat Pinecone as a derived index, not the truth.
- Use metadata filters such as `status=active`.
- Keep the SQL assistant read-only unless explicitly teaching controlled writes.
- Log retrieved chunks for observability.
- Add evaluation questions for regression testing before production releases.
- Use blue/green Pinecone namespaces for advanced rollback lessons.

## Suggested Student Labs

1. Baseline text-to-SQL without RAG.
2. Add schema docs and dense retrieval.
3. Add business-rule docs.
4. Add few-shot SQL examples.
5. Compare dense, sparse, and hybrid retrieval.
6. Publish docs from GitHub to S3.
7. Trigger ingestion from S3.
8. Debug generated SQL using retrieved context.
9. Add evaluation questions.
10. Present the architecture as a production RAG platform.
