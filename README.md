# Ultra Doc-Intelligence: Production-Grade RAG System

A **production-grade, open-source-first Retrieval-Augmented Generation (RAG) system** designed for **Transportation Management System (TMS) document Q&A**. Built with FastAPI, Next.js, and industry-grade retrieval techniques.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
![Python](https://img.shields.io/badge/Python-3.11%2B-blue)
![Node.js](https://img.shields.io/badge/Node.js-20%2B-green)
![Docker](https://img.shields.io/badge/Docker-Compose-blue)

---

## Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Retrieval Architecture](#retrieval-architecture)
- [Chunking Strategy](#chunking-strategy)
- [Confidence Scoring](#confidence-scoring)
- [Guardrails](#guardrails)
- [API Reference](#api-reference)
- [Configuration](#configuration)
- [GPU Acceleration](#gpu-acceleration)
- [Known Failure Cases](#known-failure-cases)
- [Improvement Ideas](#improvement-ideas)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

Get the system running locally in **5 minutes**:

```bash
# 1. Clone repository and cd to project root
cd rag-project

# 2. Create environment file
cp .env.example .env
# Edit .env if needed (change POSTGRES_PASSWORD, etc.)

# 3. Start all services
make up

# 4. Verify services are healthy
curl http://localhost/health

# 5. Open browser and start using
# Frontend:  http://localhost
# API Docs:  http://localhost/docs
```

**That's it!** The system will:
- Download required models (embeddings, re-ranker, LLM) on first start
- Set up PostgreSQL databases and Qdrant vector store
- Run migrations automatically
- Be ready for document uploads

### Usage After Startup

1. **Upload a document**: Drag-and-drop PDF/DOCX/TXT into the web UI
2. **Ask questions**: Type your question and get answers with sources
3. **See confidence scores**: Each answer shows retrieval quality metrics
4. **Extract structured data**: Click "Extract" to get JSON of key fields

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js + React)                    │
│  Upload · Ask Questions · Structured Extraction · Confidence UI  │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTP / REST
┌───────────────────────────▼─────────────────────────────────────┐
│                    FastAPI Backend (Python)                       │
│  /upload  /ask  /extract  /documents  /sessions  /health /metrics│
└──┬──────────────┬───────────────┬──────────────┬────────────────┘
   │              │               │              │
   ▼              ▼               ▼              ▼
Document      Embedding       Retrieval      LLM Inference
Processor     Pipeline        Engine         (Ollama / vLLM)
(unstructured)(sentence-      (Qdrant        (llama3, mistral,
              transformers)    HNSW+BM25)     deepseek-r1)
                               │
                      ┌────────▼────────┐
                      │  Re-Ranker      │
                      │  (cross-encoder)│
                      └─────────────────┘

Storage: PostgreSQL (metadata + chat sessions) · Qdrant (vectors) 
         Redis (cache/session TTL) · Local filesystem (temp files)
```

### Services

| Service | Technology | Purpose |
|---------|-----------|---------|
| **Frontend** | Next.js 15 + React 19 + TypeScript | Web UI for document Q&A |
| **Backend** | FastAPI 0.115 + Uvicorn | REST API & orchestration |
| **Vector Store** | Qdrant (HNSW) | Semantic search + similarity |
| **Metadata DB** | PostgreSQL 16 | Documents, sessions, chat history |
| **Cache** | Redis 7 | BM25 indexes, session cache, query results |
| **LLM Server** | Ollama (local) or vLLM (GPU) | LLM inference (llama3.2:3b default) |
| **Embeddings** | BAAI/bge-large-en-v1.5 | 1024-dim dense vectors, 2nd place on BEIR |
| **Reverse Proxy** | Nginx | Route `/` → frontend, `/api` → backend |

---

## Retrieval Architecture

The system implements a **multi-stage retrieval pipeline** combining industry-grade techniques for maximum recall and precision.

### 1. Dense Retrieval (Primary)

**Model**: `BAAI/bge-large-en-v1.5` (best open-source general embedding)
- Embedding dimension: 1024
- Outperforms OpenAI ada-002 on BEIR benchmarks
- **Indexing**: Qdrant with HNSW (Hierarchical Navigable Small World)
- **HNSW config**: `m=16, ef_construct=200, ef=128` (tuned for recall/speed balance)
- **Normalization**: L2 normalization for cosine similarity

**Why?** HNSW provides `O(log n)` search time with high recall. Much faster than exhaustive search with minimal quality loss.

### 2. Sparse Retrieval (BM25 — Lexical)

**Library**: `rank_bm25` (BM25Okapi variant)
- Index built **per-document** at upload time
- Stored as serialized pickle in PostgreSQL
- Cached in Redis for fast reloads

**Why?** Captures exact keyword matches, entity names (carrier IDs, shipper codes), numbers, and dates that dense embeddings might miss. Essential for logistics documents with specific identifiers.

### 3. Hybrid Retrieval with Reciprocal Rank Fusion (RRF)

**Algorithm**: Combine dense + sparse results using **RRF**, not weighted sum:

$$\text{RRF\_score}(\text{doc}) = \sum \frac{1}{k + \text{rank}_i(\text{doc})}$$

where $k=60$ (default)

**Flow**:
1. Dense retriever returns top 20 chunks
2. BM25 retriever returns top 20 chunks
3. RRF merges them → top 20 for re-ranking
4. No hyperparameter tuning needed — RRF is parameter-free and robust

**Why?** RRF is more robust to score scale differences than weighted sums. Avoids tuning `alpha` parameters.

### 4. Cross-Encoder Re-Ranking

**Model**: `cross-encoder/ms-marco-MiniLM-L-6-v2` (fast) or `BAAI/bge-reranker-large` (accurate)
- Receives full query × chunk pairs as input
- Scores each candidate holistically (not independently)
- Top-5 final candidates after re-ranking

**Why?** This is the **single highest-impact quality improvement**. Re-rankers understand query-document interaction better than independent scores.

### 5. HyDE (Hypothetical Document Embeddings) — Optional

**Process**:
1. LLM generates a hypothetical answer to the question
2. Embed the hypothesis (not the raw question)
3. Use that embedding for dense retrieval

**Example**:
```
Question: "What is the carrier rate?"
Hypothesis: "The carrier rate for this FTL shipment is $2,850.00 per mile, 
            effective from January 1 to March 31, 2025."
Result: Dense retrieval using hypothesis embedding → better recall
```

**Why?** Different phrasings of the same information exist in documents. HyDE bridges the phrasing gap.

**Control**: `HYDE_ENABLED=true` in `.env`

### 6. Contextual Chunking with Late Chunking

Each chunk stores:
- Its own text (sentence-level for precision)
- **Document-level context prefix**: `[RateConfirmation] rate_03_2025.pdf | Page 1 | `

**Why?** Solves the "ambiguous keyword" problem. A chunk about "rate" knows it's from a Rate Confirmation, not a service agreement.

### 7. Sentence-Window Retrieval

**Storage**: Chunks at sentence-level granularity for retrieval precision

**Expansion**: At retrieval time, expand each matched sentence to **±2 sentence window** for LLM context

**Trade-off**: Store sentence-granular for high precision, expand for LLM to have richer context

---

## Chunking Strategy

### Default: Semantic Chunking

**Algorithm**:
1. Split text by sentence using `nltk.sent_tokenize`
2. Group sentences into chunks where consecutive sentences have **cosine similarity > 0.7**
3. Creates "semantic paragraphs" rather than fixed-size windows

**Constraints**:
- Target size: 256–512 tokens
- Hard maximum: 512 tokens (enforced)
- Minimum: Never split mid-sentence

**Example**:
```
Text: "The carrier rate is $2,850.00. This includes fuel surcharge. 
       Equipment is a 53-foot dry van. Pickup is in Los Angeles."

Semantic chunks:
1. "The carrier rate is $2,850.00. This includes fuel surcharge."
   (similar concepts)
2. "Equipment is a 53-foot dry van. Pickup is in Los Angeles."
   (different topic → new chunk)
```

**Why?** Preserves logical coherence. A chunk contains complete thoughts, not arbitrary text boundaries.

### Fallback: Recursive Character Splitting

Used when semantic chunking produces fewer than 3 chunks (flat text detected):
- Separators: `["\n\n", "\n", ". ", " "]` (in order of preference)
- Chunk size: 400 tokens
- Overlap: 80 tokens (for context continuity)

### Both Strategies Include

- **`context_prefix`**: `f"[{doc_type}] {filename} | Page {page_num} | "`
- **`window_text`**: Chunk expanded ±2 sentences (stored separately for LLM context)
- **`chunk_index`** and **`total_chunks`**: For ordering and tracking

---

## Confidence Scoring

Each answer includes a **confidence score** (0.0–1.0) computed from **4 signals**:

| Signal | Weight | Description | Formula |
|--------|--------|-------------|---------|
| `retrieval_score` | 35% | Avg cross-encoder score of top-3 chunks | `mean([score_1, score_2, score_3])` |
| `chunk_agreement` | 25% | Semantic similarity between top chunks | `cosine_sim(embedding_1, embedding_2)` |
| `answer_coverage` | 25% | Fraction of answer tokens in retrieved chunks | `tokens_in_chunks / total_tokens` |
| `source_count` | 15% | Bonus if ≥2 independent sources support answer | `1.0 if n_sources ≥ 2 else 0.5` |

**Final score**: Weighted average of normalized signals (each 0–1)

**Interpretation**:
- **0.8–1.0** (Green): High confidence, use answer as-is
- **0.45–0.8** (Yellow): Medium confidence, prefix with "[Medium confidence]"
- **0.0–0.45** (Red): Low confidence, don't show answer, offer refusal

---

## Guardrails

### Refusal Logic

**Threshold-based**:
- If `confidence < 0.25`: Refuse with "I cannot find sufficient information..."
- If `confidence < 0.45`: Prefix answer with `[Low confidence]`
- Otherwise: Return answer normally with confidence breakdown

**Response format** (always includes):
```json
{
  "answer": "...",
  "confidence": 0.87,
  "confidence_breakdown": {
    "retrieval_score": 0.91,
    "chunk_agreement": 0.84,
    "answer_coverage": 0.79,
    "source_count": 0.85
  },
  "refused": false,
  "sources": [
    {"chunk_id": "...", "text": "...", "page": 1, "reranker_score": 0.94}
  ]
}
```

### Hallucination Detection

After LLM generates answer:
1. **Extract named entities** from answer (carriers, dates, numbers, shipment IDs)
2. **Check if entities exist** in retrieved chunks
3. If any entity is absent → **reduce confidence by 0.2**

**Example**:
```
Answer mentions: "Consignee: Acme Corp" but retrieved chunks only mention 
                 "Consignee: ABC Logistics"
→ Hallucination detected: confidence -= 0.2
```

### Threshold Tuning

Edit `.env`:
```bash
CONFIDENCE_REFUSAL_THRESHOLD=0.25      # Below this → refuse
CONFIDENCE_LOW_THRESHOLD=0.45          # Below this → prefix with "[Low confidence]"
```

---

## API Reference

All endpoints return standardized JSON with status codes.

### `POST /upload`

Upload a document for ingestion.

**Request**:
```http
POST /upload HTTP/1.1
Content-Type: multipart/form-data

file: [binary PDF/DOCX/TXT]
```

**Response** (200 OK):
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "rate_confirmation.pdf",
  "num_chunks": 34,
  "doc_type": "rate_confirmation",
  "processing_time_ms": 1240,
  "status": "ready"
}
```

**Errors**:
- `400`: Invalid file type, exceeds size limit (50 MB)
- `413`: Payload too large
- `500`: Processing error

---

### `POST /ask`

Ask a question about a document and get an answer with sources.

**Request**:
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "question": "What is the carrier rate?",
  "top_k": 5,
  "retrieval_mode": "hybrid",
  "use_hyde": true
}
```

**Parameters**:
- `doc_id` (required): Document ID from upload
- `session_id` (required): Chat session ID (create via `POST /sessions`)
- `question` (required): User question
- `top_k` (optional): Number of final chunks to use (default: 5)
- `retrieval_mode` (optional): `"dense"`, `"sparse"`, or `"hybrid"` (default: `"hybrid"`)
- `use_hyde` (optional): Enable HyDE (default: `true` if `HYDE_ENABLED=true`)

**Response** (200 OK):
```json
{
  "answer": "The carrier rate is $2,850.00 for a full truckload.",
  "confidence": 0.87,
  "confidence_breakdown": {
    "retrieval_score": 0.91,
    "chunk_agreement": 0.84,
    "answer_coverage": 0.79,
    "source_count": 0.85
  },
  "sources": [
    {
      "chunk_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "text": "Rate: $2,850.00 per FTL ...",
      "page": 1,
      "reranker_score": 0.94
    }
  ],
  "refused": false,
  "latency_ms": 823
}
```

**Errors**:
- `404`: Document not found
- `422`: Validation error
- `500`: Processing error

---

### `POST /extract`

Extract structured data from a document.

**Request**:
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response** (200 OK):
```json
{
  "shipment_id": "SHP-2025-001234",
  "shipper": "XYZ Logistics",
  "consignee": "Acme Corp",
  "pickup_datetime": "2025-01-15T08:00:00Z",
  "delivery_datetime": "2025-01-20T17:00:00Z",
  "equipment_type": "53' Dry Van",
  "mode": "FTL",
  "rate": 2850.00,
  "currency": "USD",
  "weight": 45000.0,
  "weight_unit": "lbs",
  "carrier_name": "Premier Freight"
}
```

Fields are `null` if not found in document (never hallucinated).

---

### `POST /sessions`

Create a new chat session for a document.

**Request**:
```json
{
  "doc_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response** (201 Created):
```json
{
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "title": null,
  "created_at": "2025-01-15T10:30:00Z",
  "message_count": 0
}
```

---

### `GET /sessions?doc_id={doc_id}`

List all chat sessions for a document.

**Response** (200 OK):
```json
[
  {
    "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "title": "What is the carrier rate?",
    "created_at": "2025-01-15T10:30:00Z",
    "updated_at": "2025-01-15T11:45:00Z",
    "message_count": 8,
    "last_message_preview": "The delivery is scheduled for..."
  }
]
```

---

### `GET /sessions/{session_id}/messages`

Load full conversation history for a session.

**Response** (200 OK):
```json
{
  "session_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
  "doc_id": "550e8400-e29b-41d4-a716-446655440000",
  "messages": [
    {
      "role": "user",
      "content": "What is the rate?",
      "created_at": "2025-01-15T10:31:00Z"
    },
    {
      "role": "assistant",
      "content": "The rate is $2,850.00...",
      "confidence": 0.91,
      "sources": [...],
      "created_at": "2025-01-15T10:31:05Z"
    }
  ]
}
```

---

### `GET /documents`

List all uploaded documents.

**Response** (200 OK):
```json
[
  {
    "doc_id": "550e8400-e29b-41d4-a716-446655440000",
    "filename": "rate_confirmation.pdf",
    "doc_type": "rate_confirmation",
    "num_chunks": 34,
    "status": "ready",
    "created_at": "2025-01-15T10:15:00Z",
    "chat_session_count": 3
  }
]
```

---

### `DELETE /documents/{doc_id}`

Delete a document and all associated data (chunks, vectors, sessions).

**Response** (204 No Content)

---

### `GET /health`

Health check endpoint. Verifies all service connections.

**Response** (200 OK):
```json
{
  "status": "healthy",
  "services": {
    "postgres": "ok",
    "qdrant": "ok",
    "redis": "ok",
    "ollama": "ok"
  },
  "timestamp": "2025-01-15T10:30:00Z"
}
```

**Response** (503 Service Unavailable):
```json
{
  "status": "unhealthy",
  "services": {
    "postgres": "ok",
    "qdrant": "error: Connection refused",
    "redis": "ok",
    "ollama": "error: timeout"
  }
}
```

---

### `GET /metrics`

Prometheus metrics endpoint for monitoring.

**Response** (200 OK):
```
# HELP fastapi_requests_total Total requests
# TYPE fastapi_requests_total counter
fastapi_requests_total{endpoint="/ask",method="POST",status_code="200"} 1234.0
fastapi_requests_total{endpoint="/upload",method="POST",status_code="200"} 42.0
...
```

---

## Configuration

All configuration via environment variables (`.env`). Copy `.env.example` and edit:

```bash
cp .env.example .env
```

### Database

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_HOST` | `postgres` | PostgreSQL host |
| `POSTGRES_PORT` | `5432` | PostgreSQL port |
| `POSTGRES_DB` | `dociq` | Database name |
| `POSTGRES_USER` | `dociq` | Database user |
| `POSTGRES_PASSWORD` | `changeme` | **Change this!** |

### Redis

| Variable | Default | Description |
|----------|---------|-------------|
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection URL |

### Qdrant (Vector Store)

| Variable | Default | Description |
|----------|---------|-------------|
| `QDRANT_HOST` | `qdrant` | Qdrant host |
| `QDRANT_PORT` | `6333` | Qdrant port |
| `QDRANT_COLLECTION` | `documents` | Collection name |
| `VECTOR_SIZE` | `1024` | Embedding dimension |
| `HNSW_M` | `16` | HNSW layer connections |
| `HNSW_EF_CONSTRUCT` | `200` | HNSW construction effort |
| `HNSW_EF` | `128` | HNSW search effort |

### Embeddings

| Variable | Default | Description |
|----------|---------|-------------|
| `EMBEDDING_MODEL` | `BAAI/bge-large-en-v1.5` | Embedding model |
| `EMBEDDING_BATCH_SIZE` | `32` | Batch size for embedding |
| `EMBEDDING_DEVICE` | `cpu` | `cpu` or `cuda` |

### Re-Ranking

| Variable | Default | Description |
|----------|---------|-------------|
| `RERANKER_MODEL` | `cross-encoder/ms-marco-MiniLM-L-6-v2` | Re-ranker model |

### LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_BACKEND` | `ollama` | `ollama` or `vllm` |
| `OLLAMA_BASE_URL` | `http://ollama:11434` | Ollama API URL |
| `VLLM_BASE_URL` | `http://vllm:8000` | vLLM API URL |
| `LLM_MODEL` | `llama3.2:3b` | Model name |
| `LLM_TEMPERATURE` | `0.1` | Sampling temperature |
| `LLM_MAX_TOKENS` | `1024` | Max output tokens |
| `LLM_REQUEST_TIMEOUT_SECONDS` | `60` | Request timeout |

**Alternative LLM models**:
```bash
LLM_MODEL=mistral:7b          # Better quality, slower
LLM_MODEL=deepseek-r1:8b      # Reasoning capability
LLM_MODEL=qwen2.5:7b          # Multilingual
```

### RAG Parameters

| Variable | Default | Description |
|----------|---------|-------------|
| `DENSE_TOP_N` | `20` | Dense retriever top-N |
| `SPARSE_TOP_N` | `20` | BM25 retriever top-N |
| `RERANK_TOP_K` | `5` | Final candidates after re-ranking |
| `RRF_K` | `60` | RRF parameter (higher = flatter weighting) |
| `HYDE_ENABLED` | `true` | Enable HyDE |
| `CONFIDENCE_REFUSAL_THRESHOLD` | `0.25` | Refuse below this |
| `CONFIDENCE_LOW_THRESHOLD` | `0.45` | Mark as low confidence below this |

### Session Management

| Variable | Default | Description |
|----------|---------|-------------|
| `SESSION_MAX_HISTORY_TURNS` | `10` | Max recent turns sent to LLM |
| `SESSION_SUMMARY_TRIGGER_TURNS` | `15` | Summarize older turns at this count |
| `SESSION_SUMMARY_TTL_SECONDS` | `3600` | Summary cache TTL |

### Upload

| Variable | Default | Description |
|----------|---------|-------------|
| `MAX_FILE_SIZE_MB` | `50` | Max document size |
| `ALLOWED_EXTENSIONS` | `pdf,docx,txt` | Allowed file types |

### App

| Variable | Default | Description |
|----------|---------|-------------|
| `DEBUG` | `false` | Debug mode |
| `LOG_LEVEL` | `INFO` | Logging level |
| `SECRET_KEY` | `changeme-...` | **Generate a random secret!** |
| `CORS_ORIGINS` | `http://localhost:3000,...` | CORS allowed origins |

---

## GPU Acceleration

### Enable CUDA for Embeddings

**1. Install NVIDIA CUDA Toolkit** (if not already installed):
```bash
# Windows
# Download from: https://developer.nvidia.com/cuda-downloads

# Linux
sudo apt install nvidia-cuda-toolkit
```

**2. Update `.env`**:
```bash
EMBEDDING_DEVICE=cuda
```

**3. Update `docker-compose.yml`** (backend service):
```yaml
backend:
  build: ./backend
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

**4. Restart**:
```bash
make down
make up
```

### Enable NVIDIA GPU for Ollama

**Update `docker-compose.yml`** (ollama service):
```yaml
ollama:
  image: ollama/ollama:latest
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

**Verify GPU is used**:
```bash
docker compose logs ollama | grep "compute capability"
```

### Using vLLM (GPU LLM Server)

For better LLM performance on GPU:

**1. Add vLLM service to `docker-compose.yml`**:
```yaml
vllm:
  image: vllm/vllm-openai:latest
  environment:
    MODEL_NAME: llama2-7b-hf
  deploy:
    resources:
      reservations:
        devices:
          - driver: nvidia
            count: 1
            capabilities: [gpu]
```

**2. Update `.env`**:
```bash
LLM_BACKEND=vllm
VLLM_BASE_URL=http://vllm:8000
```

---

## Known Failure Cases

### 1. Scanned PDFs Without OCR

**Problem**: PDF is just images (scanned document), no text layer
**Symptom**: Document uploads but contains no text → chunks are empty
**Solution**: 
- Add OCR processing in `document_processor.py`
- Install tesseract: `sudo apt install tesseract-ocr` (Linux) or `choco install tesseract` (Windows)
- Set `TESSDATA_PREFIX` environment variable if needed

### 2. Documents > 50 MB

**Problem**: Processing becomes very slow or runs out of memory
**Symptom**: Upload hangs or fails after 60+ seconds
**Solution**: 
- Increase `MAX_FILE_SIZE_MB` in `.env` (up to ~200 MB with 16 GB RAM)
- Consider splitting large documents into parts
- Implement async Celery processing for background ingestion (see Improvement Ideas)

### 3. Ambiguous Questions with No Exact Match

**Problem**: Question phrased differently from document language → poor retrieval
**Symptom**: Good answer should exist but question doesn't find it
**Solution**: 
- Enable HyDE: `HYDE_ENABLED=true`
- Increase `DENSE_TOP_N` and `SPARSE_TOP_N` (trade-off: slower retrieval)
- Use retrieval debug mode (`?debug=true` in UI) to inspect scores

### 4. Non-English Documents

**Problem**: BAAI/bge-large-en-v1.5 is English-focused
**Symptom**: Poor retrieval quality on French, Spanish, etc.
**Solution**: 
- For Chinese: Use `BAAI/bge-large-zh-v1.5`
- For multilingual: Use `BAAI/bge-large-multilingual-v1.5`
- Edit `EMBEDDING_MODEL` in `.env` and restart

### 5. OOM (Out of Memory)

**Problem**: System runs out of RAM during embedding or LLM inference
**Symptom**: Service crashes with `MemoryError`
**Solution**:
- Reduce `EMBEDDING_BATCH_SIZE` (e.g., 8 or 16 instead of 32)
- Use smaller embedding model: `sentence-transformers/all-MiniLM-L6-v2`
- Use smaller LLM: `llama3.2:1b` instead of `3b`
- Enable GPU: Embeddings on GPU significantly reduce RAM

---

## Improvement Ideas

These features can be implemented after core is stable:

### 1. Multi-Document Q&A

Ask questions across multiple documents simultaneously:
- User uploads 10 shipment docs
- System retrieves relevant chunks from all 10
- RRF fusion across per-document results
- Clear source attribution per document

### 2. Query Decomposition

Break down complex questions:
```
Question: "What is the rate and who is the consignee?"
Decomposed to:
  - Sub-question 1: "What is the rate?"
  - Sub-question 2: "Who is the consignee?"
Answer each independently → merge into coherent response
```

### 3. Streaming Responses

Stream LLM output token-by-token via Server-Sent Events:
```http
GET /ask/stream?doc_id=...&question=...

event: token
data: "The"

event: token
data: " carrier"

event: done
data: {"confidence": 0.87}
```

### 4. Feedback Loop

Add thumbs up/down to each answer:
- Store feedback in PostgreSQL
- Use to measure retrieval quality over time
- Retrain embeddings if feedback indicates drift

### 5. Async Document Processing

For large documents:
- Use Celery + Redis for background processing
- Return `202 Accepted` with job ID
- Poll `/jobs/{job_id}` for status
- Enables 1000+ page document support

### 6. Agentic Extraction

Tool-calling extraction instead of LLM generation:
```
LLM: "I need shipper_name, consignee, rate"
System: Provides tools: search_shipper(), search_consignee(), find_rate()
LLM: Uses tools to extract with high accuracy
```

### 7. Fine-Tuning Embeddings

Domain-specific fine-tuning on logistics documents:
- Collect Q&A pairs from system usage
- Fine-tune BAAI/bge-large on logistics pairs
- 5–10% quality improvement typical

---

## Development

### Project Structure

```
rag-project/
├── backend/                    # FastAPI backend
│   ├── app/
│   │   ├── api/routes/         # API endpoints
│   │   ├── core/               # RAG pipeline
│   │   ├── models/             # Database models
│   │   ├── services/           # Business logic
│   │   └── utils/              # Utilities
│   ├── migrations/             # Alembic migrations
│   ├── tests/                  # Pytest tests
│   ├── Dockerfile
│   ├── pyproject.toml
│   └── requirements.txt
├── frontend/                   # Next.js frontend
│   ├── src/
│   │   ├── app/                # Pages
│   │   ├── components/         # React components
│   │   ├── hooks/              # React hooks
│   │   └── lib/                # Utilities
│   ├── package.json
│   └── Dockerfile
├── nginx/
│   └── nginx.conf              # Reverse proxy
├── scripts/
│   └── bulk_ingest.py          # Bulk document ingestion
├── docker-compose.yml          # Local setup
├── .env.example                # Environment variables
├── Makefile                    # Make targets
└── README.md                   # This file
```

### Running Tests

```bash
# Unit tests
make test

# With coverage
docker compose exec backend pytest --cov=app tests/

# Integration tests only
docker compose exec backend pytest -m integration tests/
```

### Running Linters

```bash
# Python formatting
make lint
```

### Database Migrations

```bash
# Generate migration
docker compose exec backend alembic revision --autogenerate -m "Add new table"

# Apply migrations
docker compose exec backend alembic upgrade head

# Downgrade
docker compose exec backend alembic downgrade -1
```

### Common Make Targets

```bash
make up              # Start all services
make down            # Stop all services
make build           # Rebuild all images
make test            # Run tests
make lint            # Run linters
make migrate         # Run migrations
make logs            # View backend logs
make shell           # Open bash in backend container
make reset           # Reset everything (deletes data)
```

---

## Troubleshooting

### Services won't start

**Check logs**:
```bash
docker compose logs
docker compose logs backend
docker compose logs ollama
```

**Common issues**:
- Port already in use: `lsof -i :8000` (find and kill process)
- Ollama model download timeout: Re-run `make seed-ollama`
- PostgreSQL not ready: Wait 30 seconds and retry

### Ollama not responding

```bash
# Check Ollama is running
docker compose logs ollama

# Try pulling model manually
docker compose exec ollama ollama pull llama3.2:3b

# Restart Ollama
docker compose restart ollama
```

### Qdrant collection not created

```bash
# Check Qdrant status
curl http://localhost:6333/health

# Reset Qdrant data
docker compose exec qdrant rm -rf /qdrant/storage/collections/*
docker compose restart qdrant
```

### Memory issues

```bash
# Monitor memory usage
docker stats

# Reduce batch sizes in .env
EMBEDDING_BATCH_SIZE=8
```

### Files not found after upload

```bash
# Check volume mounts
docker compose exec backend ls -la /app/uploads

# Verify permissions
docker compose exec backend chmod -R 777 /app/uploads
```

---

## License

MIT License — See LICENSE file for details

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Submit a pull request

---

## Support

For issues, questions, or feature requests:
- Open an issue on GitHub
- Check existing issues and discussions
- See Troubleshooting section above

---

## Citation

If you use Ultra Doc-Intelligence in research or production, please cite:

```bibtex
@software{ultra_doc_intelligence_2025,
  title={Ultra Doc-Intelligence: Production-Grade RAG for TMS Documents},
  author={Your Organization},
  year={2025},
  url={https://github.com/yourusername/rag-project}
}
```

---

**Built with ❤️ for the logistics industry. Powered by open-source AI.**
