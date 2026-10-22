# PromiseLoop

An assistant that catches the promises you make in conversation, keeps them with the
people they belong to, and tells you what to do next.

PromiseLoop is a simulated Alexa+ style assistant for web: you talk to it, it extracts
the commitment (who, what, by when, in *your* timezone), asks before it saves
anything, and then manages the list of open promises with real dependencies.

The data layer is a real MCP (Model Context Protocol) server. The assistant never
touches the database directly - every read and write goes through MCP tools, exactly
the way a third-party assistant would use them.

---

## Stack

| Layer | Choice |
| --- | --- |
| API | FastAPI (async) + Pydantic v2 |
| Data | SQLAlchemy 2.0 async, SQLite locally, Supabase/Postgres in production |
| AI | Pluggable provider: offline `mock` or any OpenAI-compatible endpoint (OpenAI, Bedrock, Groq, Ollama...) |
| Tools | MCP server (FastMCP) with 6 tools, three transports |
| UI | React 19 + TypeScript + Vite + Tailwind v4 |

## Layout

```
backend/
  app/
    main.py            FastAPI app + lifespan
    config.py          env settings
    db.py              async engine / session
    models.py          User, Commitment, CommitmentDependency, Activity
    schemas.py         request & response models
    security.py        API key hashing
    deps.py            authentication dependencies
    routers/           health, commitments, dashboard, chat
    services/          commitment logic, dependency graph, deadline parsing
    llm/               provider, extraction, offline mock planner, agent loop
    mcp_server/        MCP server, auth context, MCP client
  migrations/001_init.sql   Postgres DDL generated from the models
  tests/                      pytest suite (62 tests)
frontend/
  src/components/      Dashboard, CommitmentCard, ChatPanel, MicButton
  src/components/ui/   hand-rolled shadcn-style primitives
  src/lib/             api client, formatting helpers
```

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv && .venv\Scripts\activate       # Windows
pip install -r requirements.txt
cp .env.example .env                                   # edit DATABASE_URL / SEED_API_KEY
python -m app.seed                                     # creates the demo user
python -m uvicorn app.main:app --reload --port 8000
```

`backend/.env` needs at least:

```
DATABASE_URL=sqlite+aiosqlite:///./promiseloop.db
SEED_API_KEY=<any long random string>
```

For production set `DATABASE_URL` to the Supabase Postgres URI and run
`migrations/001_init.sql` in the Supabase SQL editor.

Check it is alive:

```bash
curl http://127.0.0.1:8000/health
curl -H "X-API-Key: <SEED_API_KEY>" http://127.0.0.1:8000/api/commitments
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local        # put the same API key in VITE_API_KEY
npm run dev                       # http://localhost:5173
```

The Vite dev server proxies `/api` to `http://127.0.0.1:8000`, so no CORS setup is
needed for local development.

### 3. Try it

1. Open <http://localhost:5173> - the frontend sends `VITE_API_KEY` with every request.
2. Say: **"I promised Abhishek that I'll send him our project demo by tomorrow evening."**
3. The assistant extracts the promise and asks *"Shall I save this commitment?"* - nothing
   is written until you confirm.
4. Confirm, then ask: **"What should I do next?"** - the answer comes from the database
   through the MCP `get_next_actions` tool, not from the model's imagination.

## How it works

```
browser ──▶ /api/chat ──▶ agent loop ──▶ MCP session ──▶ MCP tools ──▶ database
                │              │                │
                │              │                └── list_commitments, create_commitment,
                │              │                    update_commitment, add_dependency,
                │              │                    complete_commitment, get_next_actions
                │              └── reads the tool schemas from the live MCP session
                └── returns {reply, confirmation, tools_used}
```

* **Extraction** - `services/timeparse.py` turns phrases like "tomorrow evening",
  "next Friday" or "end of the month" into a concrete date, a time and a
  `deadline_precision` (exact / day / vague / none), always in the user's timezone.
* **Confirmation gate** - `create_commitment` is a *gated* tool. The agent stages it as a
  draft and returns a confirmation card; the draft is only executed when the user
  confirms through `POST /api/chat/confirm`.
* **Provenance** - every commitment stores `source` and `original_text`, so you always
  know which sentence it came from.
* **Dependencies** - a commitment can wait on another one. Cycles are rejected, and a
  blocked commitment is not suggested until its prerequisites are done.
* **Timezone safety** - `due_at` is stored as a UTC instant plus the local date, local
  time and IANA zone, so a promise made in Delhi still reads correctly in Berlin.

## MCP transports

`MCP_TRANSPORT` in `backend/.env` picks how the assistant reaches the server:

| Transport | What happens |
| --- | --- |
| `memory` (default) | The MCP server runs in-process; still a real MCP session with real tool schemas. |
| `stdio` | Spawns `python -m app.mcp_server.server` as a subprocess - the protocol an MCP host such as Claude Desktop uses. |
| `http` | Streamable HTTP against `python -m app.mcp_server.server --http --port 8001`. The key travels in the `X-API-Key` header. |

You can also point a third-party MCP host at the server directly:

```bash
cd backend
python -m app.mcp_server.server              # stdio
python -m app.mcp_server.server --http       # streamable HTTP on :8001
```

Every tool resolves the caller from the API key in the session context and scopes its
queries to that user, so one key can never read another user's commitments.

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness, database check, active provider/transport |
| GET | `/api/commitments` | List, filter by `status`, `period`, `recipient`, `search` |
| POST | `/api/commitments` | Create one directly |
| GET | `/api/commitments/next-actions` | Prioritised list of what to do next |
| GET | `/api/commitments/{id}` | One commitment with its dependencies |
| PATCH | `/api/commitments/{id}` | Update fields |
| POST | `/api/commitments/{id}/complete` | Complete it |
| POST | `/api/commitments/{id}/dependencies` | Add a prerequisite (cycles rejected) |
| DELETE | `/api/commitments/{id}/dependencies/{depends_on_id}` | Remove a prerequisite |
| GET | `/api/commitments/{id}/activity` | Audit trail |
| GET | `/api/dashboard` | Counts, upcoming list, next actions |
| POST | `/api/chat` | Conversational turn, returns `{reply, confirmation, tools_used}` |
| POST | `/api/chat/confirm` | Executes a staged draft through MCP |

All `/api/*` routes need `X-API-Key: <key>` (or `Authorization: Bearer <key>`).

## Tests

```bash
cd backend && python -m pytest -q     # 62 passed
cd frontend && npm test               # 10 passed
cd frontend && npm run build          # type-check + production build
```

The backend suite covers the API and auth, the dependency graph and cycle prevention,
deadline parsing, the MCP tools over the in-memory and the stdio transport, and the
full chat flow (extract -> confirm -> save, and question answering through the tools).

## Notes

* No secrets are committed. `.env` files are ignored, keys are stored as SHA-256
  digests, and the raw key only ever lives in the request that needs it.
* `LLM_PROVIDER=mock` needs no key and no network - the offline planner uses the same
  extraction and the same MCP tool loop as a real model, which makes the demo
  reproducible. Point `LLM_BASE_URL`/`LLM_API_KEY` at a real model to switch over.
* Voice input uses the browser's Web Speech API (Chrome/Edge). It is a convenience,
  not a dependency.
