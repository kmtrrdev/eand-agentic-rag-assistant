# e& Egypt Agentic Knowledge Base (اتصالات مصر)

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-1.0.0-009688.svg)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-Agentic%20RAG-orange.svg)](https://github.com/langchain-ai/langgraph)
[![ChromaDB](https://img.shields.io/badge/ChromaDB-VectorStore-purple.svg)](https://www.trychroma.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

An enterprise-grade, production-quality **Agentic Retrieval-Augmented Generation (RAG)** assistant with a deterministic structured-tools layer for **e& Egypt (اتصالات مصر)** telecom packages, products, tariff pricing, and customer inquiries.

---

## Table of Contents

1. [System Architecture](#-system-architecture)
2. [LangGraph Execution Pipeline](#-langgraph-execution-pipeline)
3. [Retrieval Architecture (Dense + BM25 + Cross-Encoder)](#-retrieval-architecture)
4. [Structure-Aware Chunking](#-structure-aware-chunking)
5. [Persistent Conversation Memory](#-persistent-conversation-memory)
6. [Structured Telecom Tools](#-structured-telecom-tools)
7. [Security & Guardrails](#-security--guardrails)
8. [Evaluation Framework (Custom, RAGAS, Garak)](#-evaluation-framework)
9. [Installation & Setup](#-installation--setup)
10. [Environment Configuration](#-environment-configuration)
11. [Knowledge Base Ingestion & Re-indexing](#-knowledge-base-ingestion--re-indexing)
12. [Running the Application](#-running-the-application)
13. [Docker & Container Deployment](#-docker--container-deployment)
14. [API Reference](#-api-reference)
15. [Automated Test Suite](#-automated-test-suite)
16. [Observability & Structured Logging](#-observability--structured-logging)
17. [Telecom Domain Business Rules & Tax Handling](#-telecom-domain-business-rules--tax-handling)
18. [Project Structure](#-project-structure)
19. [Troubleshooting & FAQ](#-troubleshooting--faq)
20. [License](#-license)

---

## 🏛️ System Architecture

```
                                  [ User Request ]
                                         │
                                         ▼
                               ┌───────────────────┐
                               │ input_guard_node  │ ◄─── Prompt Injection & Secret Extraction Defense
                               └─────────┬─────────┘
                                         │ (Allowed)
                                         ▼
                               ┌───────────────────┐
                               │    intent_node    │ ◄─── Fast Classifier (Greeting vs Out-of-Scope vs Package Inquiry)
                               └─────────┬─────────┘
                   ┌─────────────────────┼─────────────────────┐
                   │ (Greeting)          │ (Out of Scope)      │ (Telecom Inquiry)
                   ▼                     ▼                     ▼
          ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
          │  greeting_node  │   │  safe_response  │   │ understand_node │
          └────────┬────────┘   └────────┬────────┘   └────────┬────────┘
                   │                     │                     │
                   │                     │                     ▼
                   │                     │            ┌─────────────────┐
                   │                     │            │  retrieve_node  │ ◄── Multi-Query Hybrid Search (Chroma + BM25)
                   │                     │            └────────┬────────┘
                   │                     │                     │
                   │                     │                     ▼
                   │                     │            ┌─────────────────┐
                   │                     │            │ evaluate_retrie │
                   │                     │            └────────┬────────┘
                   │                     │                     │
                   │                     │          ┌──────────┴──────────┐
                   │                     │          │ (Weak / Failed)     │ (Good / Max Retries)
                   │                     │          ▼                     ▼
                   │                     │  ┌───────────────┐     ┌───────────────┐
                   │                     │  │ rewrite_query │     │ generate_node │
                   │                     │  └───────┬───────┘     └───────┬───────┘
                   │                     │          │                     │
                   │                     │          └──────► [retrieve]   ▼
                   │                     │                        ┌───────────────┐
                   │                     │                        │ validate_node │
                   │                     │                        └───────┬───────┘
                   │                     │                                │
                   ▼                     ▼                                ▼
              ┌──────────────────────────────────────────────────────────────┐
              │                      output_guard_node                       │ ◄── Strips leaks, enforces formatting
              └──────────────────────────────┬───────────────────────────────┘
                                             │
                                             ▼
                                     [ Final Answer ]
```

---

## 🔄 LangGraph Execution Pipeline

The core agent is orchestrated as a stateful directed acyclic graph (`StateGraph`) with conditional routing and self-correction loops.

| Node | File Path | Functionality |
| :--- | :--- | :--- |
| `input_guard` | `app/agent/nodes/input_guard_node.py` | Validates queries against prompt injection, jailbreaks, and secret leaks. |
| `intent` | `app/agent/nodes/intent_node.py` | Fast router determining whether to bypass RAG (greetings) or search KB. |
| `greeting` | `app/agent/nodes/greeting_node.py` | Natural conversational greeting with deterministic zero-crash fallback. |
| `safe_response`| `app/agent/nodes/safe_response_node.py`| Handles out-of-scope, competitor, and unsupported service inquiries. |
| `understand` | `app/agent/nodes/understand_query.py` | Extracts intent, budget (EGP), device (phone/router), and generates sub-queries. |
| `retrieve` | `app/agent/nodes/retrieve.py` | Executes parallel multi-query hybrid search and two-stage reranking. |
| `evaluate_retrieval` | `app/agent/nodes/evaluate_retrieval.py` | Evaluates context relevance score and decides if query rewrite is needed. |
| `rewrite_query` | `app/agent/nodes/rewrite_query.py` | Reformulates search query using Arabic/English synonyms on weak retrieval. |
| `generate` | `app/agent/nodes/generate_answer.py` | Generates verified, context-grounded response with tax and USSD calculations. |
| `validate` | `app/agent/nodes/validate_answer.py` | Factual grounding verification and hallucination detection. |
| `output_guard`| `app/agent/nodes/output_guard_node.py`| Sanitizes responses, strips internal tokens, and formats final payload. |

---

## 🔍 Retrieval Architecture

The retrieval system employs a **Two-Stage Multi-Query Hybrid Pipeline**:

1. **Parallel Multi-Query Dispatch:** Searches original query, rewritten query, extracted keywords, and historical product anchors concurrently.
2. **Dense Semantic Search:** ChromaDB vector index backed by `BAAI/bge-small-en-v1.5` or `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`.
3. **Sparse Lexical Search:** BM25 (`rank_bm25`) with Arabic diacritic stripping, letter normalization, and English lemmatization.
4. **Reciprocal Rank Fusion (RRF):** Combines dense and sparse candidates.
5. **Stage 1 Reranking (Heuristic):** Filters candidates by device type (MiFi vs phone), budget bounds, and service tags.
6. **Stage 2 Reranking (Cross-Encoder):** `cross-encoder/ms-marco-MiniLM-L-6-v2` predicts deep query-document relevance (toggleable via `CROSS_ENCODER_RERANKER_ENABLED`).

---

## 🧩 Structure-Aware Chunking

Moving beyond basic character splitting, the `TelecomStructureChunker` (`app/ingestion/chunker.py`) understands telecom PDF layout semantics:

- **Package Boundary Detection:** Preserves complete pricing, quota, USSD codes, and validity within a single chunk.
- **USSD Code Anchor Tracking:** Retains `*319#`, `*130#`, `*566#`, and `*811#` within their relevant parent package chunks.
- **Metadata Enrichment:** Automatically annotates chunks with `package_name`, `chunk_type`, `parent_doc_id`, and `section_title`.
- **Legacy Fallback:** Supports `--strategy character` for backward-compatible character splitting.

---

## 🧠 Persistent Conversation Memory

- **Interface:** Abstract protocol `MemoryStore` in `app/memory/store.py`.
- **Implementation:** `SQLiteMemoryStore` in `app/memory/sqlite_store.py` with WAL mode and transaction safety.
- **Features:** Multi-turn session persistence, session isolation by `conversation_id`, and configurable sliding window limits (`MAX_HISTORY_MESSAGES`).
- **Configuration:** Set `PERSISTENT_MEMORY_ENABLED=true` in `.env`.

---

## 🛠️ Structured Telecom Tools

The system routes structured, factual questions (exact package specs, USSD codes,
tax math, budget-constrained recommendations) to deterministic tools (`app/tools/`)
instead of the RAG pipeline, so those answers are grounded in an authoritative
in-process registry rather than generated/retrieved text:

| Tool | Purpose | Parameters |
| :--- | :--- | :--- |
| `get_package_details` | Structured lookup of known packages | `package_name` (str) |
| `calculate_price` | Deterministic tax calculator (prepaid 42.86%; postpaid/Emerald 22% + flat fee, see source PDF) | `base_price` (float), `tax_type` (str) |
| `get_activation_code` | Verified USSD activation code lookup | `service` (str), `package` (str) |
| `recommendation_engine` | Budget/constraint-filtered package recommendation | called internally from the agent graph |

These are plain Python functions called directly by the agent graph
(`app/agent/nodes/mcp_tool_node.py`) — there is no separate server process or
client/server protocol; an earlier MCP (Model Context Protocol) client/server
layer was removed because everything runs in-process and the protocol boundary
added indirection without a real cross-process or cross-language need. The
`MCP_ENABLED` setting and the "MCP" naming in a few internal state fields/strategy
labels (`mcp_evidence`, `MCP_EXACT`, ...) are kept for historical continuity.

---

## 🛡️ Security & Guardrails

- **Input Guard:** RegEx + semantic analysis defending against prompt injections, DAN jailbreaks, system prompt extractions, and credential probes.
- **Output Guard:** Post-generation sanitization removing private system prompts, markdown markers, and accidental credential leaks.
- **Zero-Crash Fallback:** All critical nodes (greeting, retrieval, reranker) contain deterministic fallbacks to guarantee 100% uptime.

---

## 📊 Evaluation Framework

The project includes a 3-tier evaluation framework:

### 1. Custom LLM-as-a-Judge Evaluation (46 Benchmark Cases)
Evaluates factual correctness, hallucination resistance, guardrails, and Arabic RTL formatting.
```bash
python -m evaluation.run_evaluation
```

### 2. RAGAS Evaluation Framework
Measures `faithfulness`, `answer_relevancy`, `context_precision`, and `context_recall`.
```bash
pip install -r requirements-eval.txt
python -m evaluation.ragas.run_ragas
```

### 3. Garak Automated Red-Teaming
Automated LLM vulnerability scanning for prompt injections and data leaks.
```bash
pip install -r requirements-redteam.txt
python -m evaluation.red_team.run_garak --probes security
```

---

## 💻 Installation & Setup

```bash
# Clone and navigate to project
cd etisalat-agentic-kb

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install core dependencies
pip install -r requirements.txt
```

---

## ⚙️ Environment Configuration

Copy `.env.example` to `.env` and configure your API credentials:

```env
# LLM Settings (Azure OpenAI / OpenAI / Groq)
LLM_API_KEY=your_azure_or_openai_key
LLM_BASE_URL=https://mohammed-gpt-api.services.ai.azure.com/openai/v1
LLM_MODEL=gpt-4.1-mini

# Embeddings & Vector Store
EMBEDDING_PROVIDER=sentence_transformers
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
CHROMA_PATH=./chroma_db
COLLECTION_NAME=etisalat_knowledge

# Upgraded Feature Flags
PERSISTENT_MEMORY_ENABLED=false
MEMORY_DB_PATH=./memory.db
CHUNKING_STRATEGY=smart
CROSS_ENCODER_RERANKER_ENABLED=false
MCP_ENABLED=false
```

---

## 📥 Knowledge Base Ingestion & Re-indexing

```bash
# Structure-aware ingestion (default)
python -m app.ingestion.ingest

# Full rebuild from raw PDFs with smart chunking
python -m app.ingestion.ingest --rebuild --strategy smart

# Legacy character chunking
python -m app.ingestion.ingest --strategy character
```

---

## 🚀 Running the Application

```bash
# Start FastAPI server & Web UI
uvicorn app.api:app --host 0.0.0.0 --port 8000 --reload
```
Open **http://localhost:8000** for the web interface or **http://localhost:8000/docs** for OpenAPI Swagger.

---

## 🐳 Docker & Container Deployment

```bash
# Build and run with Docker Compose
docker-compose up --build -d

# Check health
curl http://localhost:8000/health
```

---

## 📡 API Reference

### `POST /chat`
**Request Payload:**
```json
{
  "question": "ايه باقات حكاية مكسات المتاحة؟",
  "conversation_id": "session-12345",
  "history": []
}
```

**Response Payload:**
```json
{
  "answer": "باقات حكاية مكسات تبدأ من 52 جنيه وحتى 180 جنيه...",
  "confidence": 0.95,
  "sources": [
    {
      "source": "HekayaMixat.pdf",
      "page": 1,
      "category": "mobile",
      "product": "Hekaya Mixat"
    }
  ],
  "workflow": [],
  "query_analysis": {
    "intent": "package_inquiry",
    "category": "mobile",
    "service": "Hekaya"
  },
  "conversation_id": "session-12345",
  "request_id": "a1b2c3d4"
}
```

---

## 🧪 Automated Test Suite

```bash
# Run unit & regression test suite
pytest tests/ -v
```

---

## 📈 Observability & Structured Logging

Every request logs a structured trace record:
```text
2026-08-28 14:48:52 [INFO] etisalat_kb.api request_id=a1b2c3d4 | intent=package_inquiry validation=SUPPORTED confidence=0.95 sources=3 latency_ms=840 q='ايه باقات حكاية؟'
```

---

## 📞 Telecom Domain Business Rules

- **Prepaid Tax Formula:** Total Recharge = $\text{Pre-tax Price} \times 1.4286$ (effective $42.86\%$ tax rate).
- **Core USSD Codes:**
  - Hekaya Bundles: `*319#` (or `*319*<price>#`)
  - Super Connect Data: `*566#`
  - DataLine USB / MiFi: `*130#`
  - Aqwa Card: `*811#`
  - Emerald Postpaid: Contact `111` or store visit.

---

## 📂 Project Structure

```
etisalat-agentic-kb/
├── app/
│   ├── agent/                 # LangGraph state machine & nodes
│   ├── embeddings/            # Embedding service (singleton cached)
│   ├── guardrails/            # Input/Output security & injection defense
│   ├── ingestion/             # PDF loader, structure-aware chunker, metadata
│   ├── llm/                   # Client factory & system prompt templates
│   ├── mcp/                   # Model Context Protocol server & tools
│   ├── memory/                # SQLite persistent conversation store
│   ├── retrieval/             # Hybrid retriever, BM25, cross-encoder reranker
│   ├── vectorstore/           # ChromaDB index & collection manager
│   ├── api.py                 # FastAPI application & endpoints
│   ├── config.py              # Application settings & feature flags
│   └── observability.py       # Structured logging & request metrics
├── evaluation/                # Custom LLM Judge, RAGAS, Garak red-team
├── site/                      # Multilingual frontend interface
├── tests/                     # Unit, integration, regression test suite
├── Dockerfile                 # Multi-stage production container definition
├── docker-compose.yml         # Container orchestration configuration
└── requirements.txt           # Pinned production dependencies
```

---

## 📄 License

This project is licensed under the MIT License.
