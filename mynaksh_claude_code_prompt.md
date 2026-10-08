# Build Brief: MyNaksh Personalized Astrology Chat (Shared Brain & Memory)

You are building a complete, deployed application from scratch. The design is final. Every feature, technology and behavior below was decided in advance. Your job is to implement exactly this.

---

## 0. Ground rules (read first, follow throughout)

1. **Do not invent.** Build only what this document describes. No extra features, endpoints, tables, libraries, services, or "nice to haves". If something seems missing, ask; do not fill the gap yourself.
2. **Ask when in doubt.** If any requirement is ambiguous, contradictory, or underspecified, stop and ask me one clear question before writing code for it. Prefer asking over guessing.
3. **Infrastructure details come from me, one at a time.** Never fabricate API keys, URLs, hostnames, IPs, connection strings, account names, domain names, or credentials. When a phase needs an infra value, ask me for it and wait. Use placeholders only in `.env.example`.
4. **Work in phases (Section 15).** At the end of every phase, stop, summarize what you built, show how to verify it, and wait for my approval before starting the next phase.
5. **Things explicitly NOT to build** (they will only be described in the README):
   - LangGraph or any agent framework
   - Streaming (SSE / WebSockets)
   - Redis, Kafka, queues, or any vector database
   - Password reset, email verification, OAuth, social login
   - Multilingual support (English only)
   - A real astrology engine (use the stub in Section 6)
6. **Keep the code explainable.** I must be able to explain every line in an interview. Prefer plain, readable Python over clever abstractions.
7. **Tests are required** for every phase that adds behavior (Section 14).

---

## 1. What the product does

A conversational AI service for an astrology platform. It:

- lets a user sign up, log in, and enter birth details once (onboarding);
- supports multiple chat windows per user (each window is one **session**, like ChatGPT/Claude);
- keeps **short-term context** (recent messages in the current session);
- builds a persistent **Shared Brain**: a per-user knowledge graph in Neo4j holding profile, astrology attributes, goals, interests, preferences and important memories;
- before each LLM call, **selects only the relevant context** (never the whole graph or the whole history);
- generates personalized replies through a swappable LLM layer;
- after replying, **decides in the background** whether the message contains something worth remembering, and updates the graph;
- shows the user a **"memory updated"** indicator, and a page listing what it remembers (with delete).

Core priority flow:

```
Chat → Context selection → Shared Brain → LLM → Response → Memory update
```

---

## 2. Tech stack (fixed)

**Backend**
- Python 3.11+
- FastAPI, Pydantic v2, pydantic-settings
- **PostgreSQL** via SQLAlchemy 2.0 (async) + asyncpg, with **Alembic** migrations
- Neo4j official Python driver (async API)
- LiteLLM for all LLM calls (provider-agnostic; primary + fallback model)
- `typesafe-sdk` (TypeSafe AI's **Jev** model) for classification
- LangSmith for tracing (`@traceable` on pipeline step functions; LiteLLM's LangSmith logging for LLM calls)
- bcrypt for password hashing, PyJWT for tokens
- slowapi for rate limiting
- pytest, pytest-asyncio, httpx (test client)

**Frontend**
- React SPA deployed on Vercel. **Framework details are an open decision (Section 16): ask me before starting the frontend phase.**

**Hosting**
- Frontend: Vercel (free Hobby plan)
- Backend: Docker Compose on an Oracle Cloud Always Free Ampere A1 (ARM) Ubuntu VM. The image is built on the VM itself.
- Relational DB: **Neon** (managed Postgres; I already have a Neon account and will give you the connection details)
- Graph DB: Neo4j AuraDB Free
- Local development, tests and CI: Postgres and Neo4j in Docker. Never the production databases.
- HTTPS for the backend: Cloudflare Tunnel **or** Caddy. **Open decision: ask me.**
- Tracing: LangSmith

**Orchestration**
- **No LangGraph.** A plain async pipeline: step functions operating on one explicit state object (Section 8).

---

## 3. Data split: what lives where (core design decision)

| Store | Holds | Why |
|---|---|---|
| **Postgres (Neon)** | Login credentials, app flags, sessions, messages (chat history), memory events (audit log + polling source) | Tabular, append-only data read in order: what relational databases do best |
| **Neo4j** | **The Shared Brain only**: User node with profile properties, Zodiac, LifeAreas, and Goal/Interest/Preference/Memory nodes | The graph-shaped data the assignment asks us to design |

Rules for the split:
- **One user id (uuid) for both stores.** Generated in Postgres at signup and reused as the Neo4j `User.id`.
- **No cross-store joins or transactions.** Records reference each other by id only (e.g. a memory node stores `source_message_id`; a memory event stores `memory_id`).
- **The user profile lives in Neo4j** (the assignment lists profile and astrology attributes as part of the Shared Brain). Postgres stores only `profile_complete` as an app flag.
- Write-order and failure rules are specified wherever two stores are written (Sections 6, 10).

---

## 4. Repository structure

Use this layout. Ask before deviating.

```
backend/
  app/
    main.py                 # FastAPI app, routers, CORS, rate limiter, startup (Neo4j constraints + seeding)
    config.py               # Settings (pydantic-settings) including all feature flags
    api/                    # route modules: auth, users, sessions, chat, memory, health
    auth/                   # password hashing, JWT create/verify, current-user dependency
    profile/                # profile service, sun-sign stub, static zodiac traits table
    db/                     # SQLAlchemy engine/session, ORM models, repositories (users, sessions, messages, memory_events)
    brain/                  # Neo4j driver, repository classes, Cypher queries, schema setup
    chat/                   # pipeline (TurnState, handle_turn), retrievers, prompt builder
    classifier/             # Classifier interface, JevClassifier, LLMClassifier, rules fallback
    llm/                    # LLMProvider interface, LiteLLMProvider, FakeLLM
    memory/                 # background memory task: gate, extraction, resolution, writes
    clarify/                # clarification feature (behind flag), fully isolated
    models/                 # Pydantic request/response schemas
  alembic/                  # migrations
  alembic.ini
  tests/
  Dockerfile
  requirements.txt (or pyproject.toml; ask which I prefer)
frontend/
docker-compose.yml          # production: api + tunnel/proxy (databases are managed, not in compose)
docker-compose.dev.yml      # local: api + postgres + neo4j
.env.example
.github/workflows/ci.yml
deploy.sh
README.md
```

---

## 5. Schemas

### 5a. Postgres (Alembic migrations; no `create_all` in production)

**users**
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | generated here, reused in Neo4j |
| `email` | text, unique | store lower-cased |
| `password_hash` | text | bcrypt |
| `profile_complete` | bool, default false | app flag only; profile data is in Neo4j |
| `created_at`, `updated_at` | timestamptz | |

**sessions**
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `user_id` | uuid FK → users | indexed |
| `title` | text | first user message truncated, or `"New chat"` |
| `pending_clarification` | jsonb, nullable | used only when `CLARIFY_ENABLED` |
| `created_at`, `updated_at` | timestamptz | |

**messages**
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `session_id` | uuid FK → sessions | |
| `user_id` | uuid FK → users | denormalized for ownership checks |
| `role` | text (`user` / `assistant`) | |
| `content` | text | |
| `type` | text (`answer` / `clarification`), nullable | assistant only |
| `context_used` | jsonb, nullable | assistant only |
| `used_memory_ids` | jsonb (list), nullable | assistant only; powers follow-ups |
| `route_intent` | text, nullable | assistant only |
| `route_areas` | jsonb (list), nullable | assistant only |
| `memory_status` | text (`pending` / `done` / `skipped` / `failed`), nullable | user messages only |
| `created_at` | timestamptz | |

Index: `(session_id, created_at)`.

**memory_events** (audit log of memory writes; the polling endpoint reads from here)
| Column | Type | Notes |
|---|---|---|
| `id` | uuid PK | |
| `message_id` | uuid FK → messages | the user message that produced it |
| `user_id` | uuid FK → users | |
| `action` | text (`created` / `updated` / `profile_corrected`) | |
| `memory_id` | text, nullable | Neo4j memory node id (null for profile corrections) |
| `kind`, `title`, `life_area` | text | snapshot for display |
| `created_at` | timestamptz | |

Index: `(message_id)`.

### 5b. Neo4j: the Shared Brain

**Nodes**

**User**
- Properties: `id` (same uuid as Postgres), `name`, `dob` (date), `birth_time` (time, nullable), `birth_time_known` (bool), `birth_place` (string), `language` (default `"en"`), `profile_updated_via` (`"form"` | `"chat"`), `created_at`, `updated_at`
- No email or password here.

**Zodiac** (shared; one node per sign, seeded at startup)
- Properties: `name` (e.g. `"Leo"`), `element`, `traits` (list of strings)
- Static data from a table in `profile/`.

**LifeArea** (shared; fixed closed list, seeded at startup)
- Properties: `name`
- Exactly these 9: `career`, `finance`, `relationships`, `family`, `health`, `education`, `spirituality`, `travel`, `general`
- This list is the retrieval key. The same list is used when storing memories and when routing queries. Never let the LLM invent new areas.

**Memory nodes**: four labels, one shared property set: `Goal`, `Interest`, `Preference`, `Memory`
- Properties:
  - `id`, `kind` (`goal` | `interest` | `preference` | `memory`)
  - `title` (short)
  - `text`: one clean, self-contained sentence, e.g. `"Career goal: plans to switch jobs in 2027."`
  - `life_area`
  - `attributes` (map, e.g. `timeframe`, `target_year`)
  - `confidence` (0–1), `importance` (0–1)
  - `status` (`active` | `superseded`)
  - `superseded_by` (id, nullable)
  - `created_at`, `updated_at`
  - `source_session_id`, `source_message_id` (Postgres ids)

**Relationships**

```
(User)-[:HAS_ZODIAC]->(Zodiac)
(User)-[:HAS_GOAL]->(Goal)
(User)-[:INTERESTED_IN]->(Interest)
(User)-[:PREFERS]->(Preference)
(User)-[:HAS_MEMORY]->(Memory)
(Goal|Interest|Preference|Memory)-[:ABOUT]->(LifeArea)
```

There are **no Session or Message nodes** in Neo4j.

**Startup setup** (idempotent): unique constraints on `id` for User, Goal, Interest, Preference, Memory; `MERGE`-seed the 9 LifeArea and 12 Zodiac nodes.

---

## 6. Auth, onboarding, profile

### Auth
- `POST /auth/signup` with `{email, password}`. Validate the email and require a minimum password length (ask me the minimum).
  1. Insert the Postgres `users` row (bcrypt hash, `profile_complete=false`).
  2. `MERGE` the Neo4j `User` node with the same id.
  3. If step 2 fails, delete the Postgres row (compensating action) and return 503 with a friendly message.
  4. Return `{access_token, token_type: "bearer", profile_complete}`.
- `POST /auth/login` checks Postgres only and returns the same shape.
- JWT HS256 signed with `JWT_SECRET`, `sub` = user id, expiry configurable (ask me the default).
- All other endpoints except `/health` require `Authorization: Bearer <token>`. The user is always taken from the token, never from the request body.

### Onboarding (a form, not a conversation)
- `PUT /users/me/profile` creates or updates the profile **in Neo4j**:

| Field | Required | Validation |
|---|---|---|
| `name` | yes | non-empty |
| `dob` | yes | not in the future, sensible range |
| `birth_time` | optional | omit when unknown |
| `birth_time_known` | yes | bool; false when the user ticks "I don't know" |
| `birth_place` | yes | free text |
| `language` | optional | only `"en"` accepted for now |

- The sun sign is **never** taken from the user. The backend computes it from `dob` using fixed date ranges, then (re)creates the single `HAS_ZODIAC` relationship. Changing `dob` moves the link.
- **Write order:** Neo4j profile first, then set `users.profile_complete=true` in Postgres. If the Postgres update fails, return an error (the user can retry; the Neo4j write is idempotent).
- Set `profile_updated_via="form"`.
- `GET /users/me` returns email (Postgres), the profile and zodiac (Neo4j), and `profile_complete`.

### Missing profile
- The frontend forces onboarding before chat, but **the backend must still handle `/chat` when `profile_complete=false`**: answer generically, and nudge the user to complete their birth details. Never error.

---

## 7. Sessions (Postgres)

- `POST /sessions` creates a new chat window.
- `GET /sessions` lists the current user's sessions, newest first.
- `GET /sessions/{id}/messages` returns messages in order (own sessions only → otherwise 404).
- Short-term context = **the last 6 messages** of the current session from Postgres (configurable `HISTORY_WINDOW=6`).

---

## 8. Chat pipeline (`POST /chat`)

### Request / response

```json
// request
{ "session_id": "session-456", "message": "What should I focus on in my career?" }

// response
{
  "response": "Based on your goal of switching jobs in 2027...",
  "user_id": "user-123",
  "session_id": "session-456",
  "message_id": "msg-789",
  "type": "answer",
  "options": null,
  "context_used": ["user_profile", "zodiac", "history", "goal:<id>"]
}
```

- `message_id` is the **user** message's id, used for memory polling (Section 10).
- `type` is always `"answer"` unless the clarify flag is on (Section 11).

### State object and steps (plain async functions)

```python
@dataclass
class TurnState:
    user_id: str
    session: SessionRow
    message: str
    history: list[MessageRow]
    profile: Profile | None = None
    route: RouteResult | None = None
    memories: list[MemoryNode] = field(default_factory=list)
    context_used: list[str] = field(default_factory=list)
    reply: str | None = None
```

Each step function is decorated with LangSmith `@traceable`. Order:

1. Validate input and verify session ownership (Postgres). Load the profile and zodiac (Neo4j).
2. Load the last `HISTORY_WINDOW` messages (Postgres).
3. *(clarify flag only)* Resolve a pending clarification (Section 11).
4. **Route** via the classifier (Section 9).
5. *(clarify flag only)* Check clarify triggers; if one fires, return a clarification.
6. **Retrieve** using `RETRIEVERS[route.intent]` (Neo4j; table below).
7. **Build the prompt** (labeled blocks, below).
8. **Generate** via the LLM layer.
9. **Save** both messages in Postgres in one transaction:
   - the user message, with `memory_status` = `pending` or `skipped`;
   - the assistant message, with `context_used`, `used_memory_ids`, route fields and `type`.
   Update the session `updated_at`, and set its title from the first message.
10. **Respond**, then schedule the background memory task (FastAPI `BackgroundTasks`) unless the gate already said skip.

### Retrievers by intent

| Intent | What is retrieved |
|---|---|
| `general` | Compact profile + zodiac + top-K (`TOP_K_MEMORIES=5`) **active** memories whose `life_area` is in `route.areas` |
| `followup` | Profile + zodiac + **exactly the memories in the previous assistant message's `used_memory_ids`** (from Postgres), fetched from Neo4j by id. No new search. |
| `memory_query` | **All** active memories in `route.areas`; if the user asks about everything / no area detected, all active memories. Newest first. No astrology flavor in the prompt. |
| `profile_query` | Profile + zodiac only |
| `smalltalk` | User's name only + last 2 messages |

**Ranking (general):**

```
score = confidence × importance × recency_decay
recency_decay = exp(-days_since_updated / RECENCY_HALF_LIFE_DAYS)   # config, default 90
```

- Never select `status = 'superseded'`. A follow-up whose memory was since deleted simply skips it.
- If `route.areas` is empty, or contains only `general` with nothing found: take the top 3 active memories by importance across all areas.

### Prompt structure (labeled blocks)

```
[SYSTEM]  persona + rules
[PROFILE] name · dob · birth place · birth time (or "unknown") · sun sign + element + traits
[MEMORY]  one line per selected memory: "- <kind> (<life_area>): <text> (stated <relative date>)"
[HISTORY] recent messages
[USER]    current message
```

System prompt rules (write the exact wording and show it to me in the phase summary):
- You are a warm, practical astrology guide; astrology flavor comes from the stub sign data.
- Use the user facts only when relevant to the question.
- Never invent facts about the user; if something is not known, say so.
- If the profile is incomplete, answer generally and suggest completing birth details.
- With `CLARIFY_ENABLED=false`: "Do not ask clarifying questions. Make a reasonable assumption and state it briefly."
- With `CLARIFY_ENABLED=true`: "If the question is ambiguous and the answer depends on it, ask one short clarifying question."

### `context_used`
List exactly what was injected: `"user_profile"`, `"zodiac"`, `"history"`, and `"<kind>:<id>"` per memory. Tests assert on this field.

---

## 9. Classifier (router)

### Interface

```python
class Classifier(Protocol):
    async def route(self, history: list[MessageRow], message: str) -> RouteResult: ...

@dataclass
class RouteResult:
    intent: Literal["general", "followup", "memory_query", "profile_query", "smalltalk"]
    intent_confidence: float
    areas: list[str]            # subset of the 9 LifeAreas
    has_durable_fact: float     # 0–1, memory gate score
    source: Literal["jev", "llm", "rules"]
```

### JevClassifier (primary, `CLASSIFIER=jev`)
One `system_one` call per message. The state is the last 2–3 messages plus the new message. Questions:
- `intent`: **Choice** over the 5 intents, each with a one-line description.
- `area_<name>`: one **Noul** per area for the 8 non-`general` areas ("The new user message is about …"). Areas scoring ≥ `AREA_THRESHOLD` (default 0.5) are kept; if none qualify, `areas = ["general"]`.
- `has_durable_fact`: **Noul**: "The new user message states a lasting personal fact, goal, preference, or life event worth remembering."
- Pin the model with `JEV_MODEL` (default `jev-1.13.0`; confirm with me). Never use `jev-latest`.
- If the SDK client is synchronous, call it with `asyncio.to_thread`. Check the SDK and tell me which applies.
- Apply a timeout (ask me the value).

### Fallback chain
1. Jev intent confidence < `ROUTER_MIN_CONFIDENCE` (default 0.7), or a Jev error/timeout → **LLMClassifier** (structured JSON via the LLM layer, same `RouteResult` fields).
2. LLM also fails → **rules** (keyword lists per area, simple patterns for follow-up / memory questions / small talk). `has_durable_fact` = 1.0 in this case, so extraction still runs.

`CLASSIFIER=llm` makes the LLMClassifier primary (Jev skipped).

---

## 10. Background memory task

Runs after the response via FastAPI `BackgroundTasks`. Every step is traceable.

1. **Gate.** If `MEMORY_GATE_ENABLED` and `has_durable_fact < MEMORY_GATE_THRESHOLD` (default 0.5): the user message is saved with `memory_status='skipped'` and no task is scheduled.
2. **Extraction (one LLM call, structured JSON).** Input: the user message, the last 2 messages for context, the user's existing active memories (id + kind + life_area + text) and the current profile. Output: a list of items:

```json
{
  "action": "create | update | skip",
  "target_id": "existing memory id when action=update, else null",
  "kind": "goal | interest | preference | memory | profile_correction",
  "title": "...",
  "text": "one clean self-contained sentence",
  "life_area": "one of the 9",
  "attributes": {},
  "profile_field": "name | dob | birth_time | birth_place (profile_correction only)",
  "profile_value": "...",
  "confidence": 0.0,
  "importance": 0.0
}
```

Extraction rules (put them in the prompt):
- **Store:** stable facts, goals, preferences, interests, significant life events.
- **Do not store:** greetings, questions, passing moods, the assistant's own statements or predictions, anything already stored with the same meaning (→ `skip`).
- `life_area` must be one of the 9; validate and reject otherwise.

3. **Apply to Neo4j.**
   - `create`: new node with the right label, `ABOUT` its LifeArea, with `source_message_id` and `source_session_id`.
   - `update`: mark the old node `status='superseded'`, `superseded_by=<new id>`; create the new active node.
   - `profile_correction`: update the User property and set `profile_updated_via='chat'`. If `dob` changed, recompute the zodiac link.
   - Validate all LLM output with Pydantic. Invalid items are dropped and logged.
4. **Record in Postgres** (only after the Neo4j writes succeed): insert one `memory_events` row per applied item, then set the user message's `memory_status='done'`.
5. **Failure handling:**
   - On any error, set `memory_status='failed'` and log it.
   - If Neo4j succeeded but the Postgres write failed, log the inconsistency clearly. The memory exists in the brain; only its event/status is missing. This is acceptable because memory writes are best-effort.
   - Failures never affect the chat response.

### Memory polling (Postgres only)
- `GET /messages/{message_id}/memory-updates` returns `{status, updates: [{action, kind, title, life_area, memory_id}]}`, read from `messages.memory_status` and `memory_events` (own messages only).
- The frontend polls every 1 s, up to 8 s, until status ≠ `pending`, then shows a chip like "Memory updated: Career goal · switch jobs (2027)" linking to the memory page.

### Memory page APIs (Neo4j)
- `GET /users/me/memory` returns active memories grouped by life area, plus the profile summary.
- `DELETE /users/me/memory/{id}` hard-deletes the node (`DETACH DELETE`), own memories only. Past `memory_events` rows stay as history.

---

## 11. Clarifying questions (behind `CLARIFY_ENABLED`, default **false**)

All code lives in `clarify/`. With the flag off, none of it runs and the API never returns `type: "clarification"`.

**Triggers** (checked after routing, only when the flag is on):
- **Missing profile field:** the question asks about specific timing or dates (one extra Jev Noul, asked only when the flag is on) and `birth_time_known=false`.
- **Ambiguous reference:** a vague reference ("it", "that") and 2 or more active memories from different areas with similar scores.
- **No area detected:** all area scores are low and intent is `general`.

**Behavior:**
- Return a short templated question (no generation LLM call) with `type: "clarification"` and `options` (labels built from the candidate memories or areas). Save both messages as usual.
- Save `pending_clarification` on the Postgres session: `{question, options: [ids or areas], original_message}`.
- On the next turn, if a pending clarification exists, a Jev Choice over the options plus "none / new topic" decides:
  - **Matched:** answer the **original** message using the chosen memory or area, then clear the pending state.
  - **New topic:** clear the pending state and continue normally.
- At most one clarification per turn. Never ask when a reasonable answer is possible.

**Tests** for this feature live in their own file, with a fixture forcing the flag on.

---

## 12. Feature flags and config (all in `config.py`, all from env)

| Setting | Default | Purpose |
|---|---|---|
| `CLARIFY_ENABLED` | `false` | Clarifying questions |
| `USE_EMBEDDINGS` | `false` | Reserved for a later, optional phase. **Do not implement unless I ask.** |
| `CLASSIFIER` | `jev` | `jev` or `llm` |
| `MEMORY_GATE_ENABLED` | `true` | Skip extraction on low gate score |
| `HISTORY_WINDOW` | `6` | |
| `TOP_K_MEMORIES` | `5` | |
| `ROUTER_MIN_CONFIDENCE` | `0.7` | |
| `AREA_THRESHOLD` | `0.5` | |
| `MEMORY_GATE_THRESHOLD` | `0.5` | |
| `RECENCY_HALF_LIFE_DAYS` | `90` | |
| `PRIMARY_MODEL`, `FALLBACK_MODEL` | **ask me** | LiteLLM model strings |
| `JEV_MODEL` | `jev-1.13.0` | Confirm with me |

Other env (values come from me): `DATABASE_URL` (Neon), `JWT_SECRET`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `TYPESAFE_API_KEY`, provider API keys, `LANGSMITH_API_KEY`, `LANGSMITH_TRACING`, `LANGSMITH_PROJECT`, `CORS_ORIGINS`.

### Neon specifics
- Neon requires SSL. Configure the asyncpg connection accordingly.
- Neon offers a **pooled** (PgBouncer) and a **direct** connection string. Ask me which one I'm providing.
  - **Pooled:** asyncpg's prepared-statement cache must be disabled (e.g. `prepared_statement_cache_size=0` / `statement_cache_size=0`).
  - **Migrations:** run Alembic against the **direct** connection string.
- Neon's free tier suspends idle compute, so the first query after idle is slower. Use sensible connection timeouts and `pool_pre_ping`.

### LLM layer

```python
class LLMProvider(Protocol):
    async def generate(self, messages: list[dict]) -> str: ...
    async def generate_json(self, messages: list[dict], schema: type[BaseModel]) -> BaseModel: ...
```

- `LiteLLMProvider`: primary model with retry, then automatic fallback to `FALLBACK_MODEL` on error or rate limit.
- `FakeLLM`: deterministic, for tests.
- Switching provider = changing env values only.

---

## 13. Error handling

| Case | Behavior |
|---|---|
| Invalid input | 422 via Pydantic |
| Unauthenticated / other user's resource | 401 / 404 |
| Missing profile | Generic answer + nudge (Section 6) |
| Jev failure | LLM classifier, then rules (Section 9) |
| Primary LLM failure | Fallback model; if both fail, a friendly "please try again" reply (HTTP 200, `type: "answer"`, `context_used: []`), never a stack trace |
| **Neo4j unavailable during chat** | Answer using history only, `context_used: ["history"]`; skip memory extraction (`memory_status='failed'`); log it |
| **Postgres unavailable** | `/chat`, auth and sessions cannot work: return 503 with a friendly message. No partial writes to Neo4j. |
| Empty memory / no relevant context | Normal answer, no memory block; the prompt rules prevent invented facts |
| Extraction or cross-store write failure | Section 10 rules; chat unaffected |
| `/health` | Reports Postgres and Neo4j status separately |

---

## 14. Testing

- pytest + pytest-asyncio + httpx.
- `FakeLLM` and `FakeClassifier` (scripted `RouteResult`s), so tests never call real APIs.
- **Postgres and Neo4j for tests run in Docker** (local) and as GitHub Actions service containers (CI). Never Neon or AuraDB.
- Alembic migrations run against the test Postgres before the suite (this also tests the migrations).
- **Required scenarios** (the assignment's list), each asserting on the response and `context_used`:
  1. New user (no profile) gets a generic answer with a nudge
  2. Creating a long-term memory ("I'm planning to switch jobs next year" → Goal node, career, target_year 2027, plus a `memory_events` row)
  3. Retrieving a memory in a later message ("What should I focus on for my career?" → `context_used` contains the goal)
  4. Follow-up ("Why do you say that?" → same memories as the previous turn, via `used_memory_ids`)
  5. New session using previous information ("What do you remember about my career goals?")
  6. Irrelevant memory (a health question must not include the career goal in `context_used`)
  7. User correcting existing information (old memory superseded; profile correction updates User and zodiac)
  8. Missing user information
- Also test:
  - signup compensation (Neo4j failure removes the Postgres user),
  - auth,
  - session isolation between users,
  - memory gate skip,
  - LLM fallback,
  - Neo4j-down fallback,
  - Postgres-down 503,
  - memory polling statuses,
  - memory delete.
- Clarify tests in a separate file (flag forced on).

---

## 15. Build phases (stop and wait for approval after each)

0. **Kickoff:** read this brief, list every question and open decision (Section 16), and wait for my answers.
1. **Scaffolding:**
   - repo layout and config with flags;
   - `docker-compose.dev.yml` (api + postgres + neo4j);
   - SQLAlchemy setup, Alembic with the initial migration (all 4 tables);
   - Neo4j schema setup and seeding;
   - `/health` reporting both databases;
   - CI running migrations and an empty test suite.
2. **Hello deploy:** deploy the skeleton to the Oracle VM over HTTPS, connected to Neon (migrations applied) and AuraDB, with `/health` green. **Ask me for each infra detail as you need it** (Neon connection strings, AuraDB credentials, VM access, tunnel/domain).
3. **Auth + profile + onboarding APIs**: two-store signup with compensation, sun-sign stub, tests.
4. **Sessions and messages** APIs (Postgres) and tests.
5. **LLM layer** (LiteLLM + FakeLLM) and **classifier** (Jev + LLM + rules fallback), with tests.
6. **Chat pipeline:** retrievers, prompt builder, save, response, `context_used`. Scenarios 1, 3, 4, 6, 8.
7. **Background memory task:** gate, extraction, resolution, profile corrections, `memory_events`, polling endpoint, memory page APIs. Scenarios 2, 5, 7.
8. **Frontend:** signup/login, onboarding form ("I don't know" checkbox for birth time), chat window with a sessions sidebar, memory-updated chip via polling, memory page with delete, profile edit, and a "waking up the server" state. Deploy to Vercel.
9. **Production hardening:** rate limiting on `/chat`, CORS locked to the Vercel domain, LangSmith tracing verified end to end, deploy script (pull, migrate, rebuild), keep-alive ping setup.
10. **README** (Section 17).
11. **Clarifying questions** behind `CLARIFY_ENABLED` (still default off), with their own tests.

---

## 16. Open decisions: ask me before the relevant phase

- Frontend framework details (React + Vite vs. Next.js) and styling approach
- HTTPS for the backend: Cloudflare Tunnel or Caddy (+ domain)
- `PRIMARY_MODEL` and `FALLBACK_MODEL`
- `requirements.txt` vs. `pyproject.toml`
- JWT expiry, minimum password length, Jev timeout
- Confirm `JEV_MODEL` version
- Neon: pooled vs. direct connection string; a separate Neon database/branch for this project
- Anything else you find unclear

---

## 17. README contents (required by the assignment)

1. Overview and live links
2. Architecture (diagram + request flow + background memory flow)
3. Data design:
   - the Postgres vs. Neo4j split and why;
   - the Postgres tables;
   - the Shared Brain graph schema (nodes, relationships, why a graph);
   - cross-store rules (shared ids, write order, failure handling)
4. Memory strategy: short-term (Postgres history) vs. long-term (Neo4j), the gate, what is and isn't stored, update/supersede logic, profile corrections
5. Context-selection approach: Jev router, intents, life areas as the retrieval key, per-intent retrieval, ranking, fallback chain
6. Key design decisions and trade-offs, including:
   - **Why not LangGraph:** use the text I'll provide, or draft it from this brief and show me
   - **Polyglot persistence:** why chat history and auth live in Postgres and only the Shared Brain lives in Neo4j; the cost (no cross-store transactions, compensating actions, best-effort memory writes)
   - **Streaming (SSE):** not built; why polling was chosen, plus the extra work and failure modes (proxy buffering, dropped connections, idle timeouts, mid-stream errors, double sends)
   - **Embeddings:** not built; how they would rank memories across areas, the "similar ≠ relevant" caveat, why area filtering was chosen first
   - **Jev vs. LLM router** (calibrated confidence, cost) and that OpenAI's Decisions API is an alternative behind the same interface
   - **Clarifying questions** behind a feature flag
7. Production considerations: **leave a clearly marked placeholder; I will provide this section's content.**
8. Evaluation: how we'd measure memory accuracy, context relevance, personalization, conversation consistency, irrelevant context and memory persistence
9. Setup, env vars, migrations, running tests, deployment
10. Sample API requests and responses for every endpoint

---

Start with **Phase 0**: confirm you've read everything, then list your questions and the open decisions. Do not write code yet.
