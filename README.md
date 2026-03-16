# PartSelect Chatbot

An AI-powered customer support assistant for Whirlpool/KitchenAid dishwasher and refrigerator parts. Helps users find compatible parts, diagnose symptoms, look up prices, and get installation guidance.

---

## Tech Stack

| Layer | Technology |
|---|---|
| **LLM (agent)** | Claude Sonnet 4.6 via Anthropic API |
| **LLM (guardrail)** | Claude Haiku 4.5 — fast intent classification |
| **Embeddings** | OpenAI `text-embedding-3-small` |
| **Agent framework** | LangGraph state machine + LangChain tools |
| **Backend** | FastAPI + asyncpg |
| **Database** | PostgreSQL 16 + pgvector extension |
| **Frontend** | React 18, Ant Design, Framer Motion |
| **Containerization** | Docker Compose (Postgres + pgvector) |

---

## Architecture

```
User message
     │
     ▼
┌─────────────┐   out of scope / greeting
│  Guardrail  │ ─────────────────────────► Direct response (END)
│  (Haiku)    │
└─────────────┘
     │ in scope
     ▼
┌─────────────┐   needs model number
│   Context   │ ─────────────────────────► Ask user (END)
│  Extractor  │
└─────────────┘
     │ context ok
     ▼
┌─────────────┐
│    Agent    │ ◄──────────────────────────┐
│  (Sonnet)   │                            │
└─────────────┘                            │
     │ tool_calls                          │
     ▼                                     │
┌─────────────┐                            │
│    Tools    │ ── execute_sql ────────────┘
│   (async)   │ ── semantic_search ────────┘
└─────────────┘
     │ done
     ▼
  Response
```

**Two tools:**
- `execute_sql` — LLM writes validated SELECT queries for structured lookups (compatibility, prices, reviews, part numbers)
- `semantic_search` — pgvector cosine similarity across parts, expert Q&As, and repair stories in parallel (for vague symptom descriptions)

**Why LangGraph:** encodes conversation logic as an explicit state machine — deterministic routing for model number collection, guardrailing, and tool use. No surprises in a customer-facing demo.

**Session state** is checkpointed per `session_id` via `MemorySaver`:
```python
class ChatState(TypedDict):
    messages: list[BaseMessage]
    appliance_type: str | None      # "dishwasher" | "refrigerator"
    model_number: str | None        # e.g. "WDT750SAHZ0"
    model_confidence: str           # "none" | "partial" | "confirmed"
    intent_category: str | None
    is_in_scope: bool
```

---

## Quick Start

### Prerequisites
- Python 3.11+
- Docker + Docker Compose
- [Anthropic API key](https://console.anthropic.com/) (agent + guardrail)
- [OpenAI API key](https://platform.openai.com/) (embeddings only — costs ~$0.002 for seed data)
- Node.js 18+ (frontend only)

### 1. Clone and install

```bash
git clone <repo-url>
cd partselect-chatbot
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Configure environment

```bash
cp .env.example .env
# Open .env and fill in ANTHROPIC_API_KEY and OPENAI_API_KEY
```

### 3. Start Postgres

```bash
docker-compose up -d
# Postgres starts on localhost:5432
# schema.sql runs automatically via docker entrypoint
```

### 4. Load seed data

The repo includes pre-built seed data (25 parts, 9 appliance models, Q&As, repair stories):

```bash
python db/load_excel.py partselect_real_data_1.xlsx
python db/load_excel.py partselect_real_data_2.xlsx
```

### 5. Generate embeddings

```bash
python db/generate_embeddings.py
# Calls OpenAI text-embedding-3-small for ~43 rows, builds IVFFlat indexes
# Cost: ~$0.002 total
```

### 6. Run

**Terminal chat (no frontend needed):**
```bash
python scripts/chat.py
```

**API server + React frontend:**
```bash
# Terminal 1
uvicorn app.main:app --reload
# API at http://localhost:8000, docs at http://localhost:8000/docs

# Terminal 2
cd case-study && npm install && npm start
# Frontend at http://localhost:3000
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | ✓ | — | Agent (Sonnet) + guardrail (Haiku) |
| `OPENAI_API_KEY` | ✓ | — | Embeddings only |
| `DATABASE_URL` | ✓ | `postgresql://partselect:partselect@localhost:5432/partselect` | Postgres connection string |
| `AGENT_MODEL` | | `claude-sonnet-4-6` | Agent model |
| `GUARDRAIL_MODEL` | | `claude-haiku-4-5-20251001` | Guardrail model |
| `EMBEDDING_MODEL` | | `text-embedding-3-small` | Embedding model |
| `SEMANTIC_SEARCH_LIMIT` | | `8` | Results per source in semantic search |
| `SQL_RESULT_LIMIT` | | `20` | Max rows per SQL query |
| `SQL_TIMEOUT_SECONDS` | | `5` | Query timeout |

---

## Project Structure

```
partselect-chatbot/
├── app/
│   ├── agent/
│   │   ├── graph.py          # LangGraph state machine wiring
│   │   ├── nodes.py          # Node functions + routing logic
│   │   ├── prompts.py        # All prompts
│   │   └── state.py          # ChatState TypedDict
│   ├── tools/
│   │   ├── sql_tool.py       # Text-to-SQL with injection prevention
│   │   └── semantic_tool.py  # pgvector similarity search (3 sources in parallel)
│   ├── api/routes.py         # POST /api/v1/chat endpoint
│   ├── config.py             # Pydantic settings from .env
│   ├── database.py           # asyncpg connection pool
│   └── main.py               # FastAPI app + CORS
├── db/
│   ├── schema.sql            # PostgreSQL schema (auto-runs in Docker)
│   ├── load_excel.py         # Excel → Postgres loader (idempotent)
│   └── generate_embeddings.py # Populates vector columns + builds indexes
├── scripts/chat.py           # Rich terminal chat interface
├── case-study/               # React frontend (CRA)
├── partselect_real_data_1.xlsx  # Seed data (parts, models, Q&As)
├── partselect_real_data_2.xlsx  # Seed data (repair stories, reviews)
├── docker-compose.yml
├── requirements.txt
└── .env.example
```

---

## Terminal Chat Commands

| Command | Description |
|---|---|
| `/help` | Show example questions |
| `/context` | Show current session state (model number, appliance type) |
| `/debug` | Toggle tool call visibility |
| `/clear` | Start a new session |
| `/quit` | Exit |

---

## Seed Data Coverage

25 parts across dishwashers and refrigerators, 9 appliance models, 10+ expert Q&As, 8+ repair stories with difficulty/time/tools info, compatibility mappings, and symptom fix-rate percentages.

To scale to the full PartSelect catalog: scrape `partselect.com/Models/{model_number}/` with Playwright, insert in the same Excel format, and re-run `generate_embeddings.py` (it skips already-embedded rows). Swap `MemorySaver` for `AsyncRedisSaver` for multi-process session persistence.
