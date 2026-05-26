# Qorvexis

Qorvexis is an infrastructure orchestration platform for AI workloads. The current build includes Phase 1 platform foundations, Phase 2 inference integration, Phase 3 operational intelligence, and Phase 4 request orchestration.

Qorvexis is infrastructure-first, backend-heavy, and enterprise-oriented. It is not a chatbot, not an AI assistant, and not a frontend-focused application.

## Current Architecture

```text
User Prompt
  -> Frontend Operational Dashboard
  -> FastAPI Route
  -> Operational Session Memory
  -> Request Classification
  -> Priority Assignment
  -> In-Memory Execution Queue
  -> Execution Scheduler
  -> Provider Capacity Check
  -> Inference Service
  -> Provider Selection
      -> Gemini 2.5 Flash
      -> Groq llama-3.3-70b-versatile
  -> Optional Provider Failover
  -> Normalized Response + Metadata
  -> Supabase PostgreSQL Persistence
  -> Metrics Aggregation
  -> Frontend Operational Dashboard
```

## Project Structure

```text
Qorvexis/
|-- app.py
|-- README.md
|-- frontend/
|   |-- index.html
|   |-- style.css
|   `-- script.js
`-- backend/
    |-- .env
    |-- requirements.txt
    `-- app/
        |-- main.py
        |-- settings.py
        |-- routes/
        |   |-- ask.py
        |   |-- metrics.py
        |   |-- sessions.py
        |   `-- schemas.py
        |-- services/
        |   |-- analytics_service.py
        |   |-- inference_service.py
        |   |-- request_service.py
        |   `-- session_service.py
        |-- providers/
        |   |-- base.py
        |   |-- gemini_provider.py
        |   `-- groq_provider.py
        |-- database/
        |   |-- session.py
        |   `-- health.py
        |-- orchestration/
        |   |-- capacity.py
        |   |-- lifecycle.py
        |   |-- queue_manager.py
        |   `-- scheduler.py
        `-- models/
            |-- inference_session.py
            |-- request_lifecycle_event.py
            `-- request_log.py
```

## One-File Local Run

```bash
python app.py
```

The launcher compiles backend files, installs missing dependencies, starts FastAPI on `http://127.0.0.1:8000`, and serves the frontend on `http://127.0.0.1:5500`.

Use `Ctrl+C` to stop both services.

## Environment Variables

Configure `backend/.env`:

```env
APP_NAME=Qorvexis API
SUPABASE_URL=https://zehwarxzilcxssqigvul.supabase.co
DATABASE_URL=postgresql+psycopg2://postgres.<project-ref>:YOUR_DATABASE_PASSWORD@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres?sslmode=require&connect_timeout=8
GEMINI_API_KEY=your_gemini_key
GROQ_API_KEY=your_groq_key
PROVIDER_TIMEOUT_SECONDS=30
MAX_CONCURRENT_REQUESTS=2
GEMINI_MAX_CONCURRENCY=1
GROQ_MAX_CONCURRENCY=1
CORS_ORIGINS_RAW=http://127.0.0.1:5500,http://localhost:5500
```

For Supabase local development, the Session pooler connection string is recommended when direct database networking is unavailable.

## Request Classification

Phase 3 classifies requests deterministically into:

- `coding`
- `debugging`
- `infrastructure`
- `reasoning`
- `general`

The classifier is rule-based and lives in `backend/app/services/inference_service.py`.

## Operational Sessions And Memory

Qorvexis supports persisted operational sessions. This gives users a "new session" workflow and continuity memory without repositioning the product as a chatbot.

Session behavior:

- `POST /sessions` creates a new operational session
- `GET /sessions` lists recent sessions
- `GET /sessions/{session_id}/requests` returns persisted session history
- `POST /ask` accepts an optional `session_id`
- if no session is supplied, the backend creates one
- recent successful requests in the same session are included as memory context for the next inference

Memory is scoped to the active session and is currently limited to the most recent successful requests.

## Provider Routing

Routing remains simple and modular:

- prompts that look like code, copied errors, stack traces, package issues, SQL/API failures, or debugging requests use Groq first
- all other prompts use Gemini first

This is a routing foundation, not advanced ML routing.

## Failover Logic

If the selected provider fails, Qorvexis attempts the alternate provider:

- Groq failure -> Gemini fallback
- Gemini failure -> Groq fallback

The response includes:

- `provider`
- `original_provider`
- `fallback_used`
- `model`
- `category`
- `latency_ms`

## Request Orchestration

Phase 4 adds a lightweight in-memory execution queue and scheduler. This keeps Qorvexis monolithic while introducing control-plane behavior for workload execution.

Lifecycle states:

- `queued`
- `scheduled`
- `executing`
- `completed`
- `failed`
- `cancelled`
- `fallback_executing`

Priority levels:

- `critical`
- `high`
- `normal`
- `low`

Priority assignment is deterministic:

- production outage / critical language -> `critical`
- debugging and infrastructure workloads -> `high`
- summaries and lightweight overview requests -> `low`
- all other requests -> `normal`

Provider capacity controls:

- `MAX_CONCURRENT_REQUESTS`
- `GEMINI_MAX_CONCURRENCY`
- `GROQ_MAX_CONCURRENCY`

The queue manager records queue wait time, execution duration, lifecycle transitions, and provider capacity state.

## API

### `GET /health`

```json
{
  "status": "ok",
  "service": "Qorvexis API",
  "database": "connected",
  "database_error": null
}
```

### `POST /ask`

Request:

```json
{
  "prompt": "debug this python function",
  "session_id": "optional-session-id"
}
```

Response:

```json
{
  "request_id": 184,
  "session_id": "1f5b70f1-c4b4-46b6-9095-eeaacd553320",
  "provider": "groq",
  "original_provider": "groq",
  "fallback_used": false,
  "model": "llama-3.3-70b-versatile",
  "category": "coding",
  "priority": "high",
  "lifecycle_state": "completed",
  "queue_wait_ms": 52,
  "execution_duration_ms": 417,
  "response": "...",
  "latency_ms": 469
}
```

### `POST /sessions`

```json
{
  "title": "Incident review"
}
```

### `GET /sessions`

Returns recent operational sessions.

### `GET /sessions/{session_id}/requests`

Returns the persisted request history for one session.

## Metrics APIs

Phase 3 adds operational metrics endpoints:

```text
GET /metrics/overview
GET /metrics/providers
GET /metrics/latency
GET /metrics/categories
GET /metrics/queue
GET /metrics/capacity
GET /metrics/throughput
GET /metrics/lifecycle
```

These endpoints aggregate:

- total requests
- successful requests
- failed requests
- provider distribution
- provider failure counts
- provider success rates
- average latency
- latency by provider
- request category counts
- fallback usage
- queue depth
- active executions
- provider capacity
- throughput
- lifecycle states
- priority distribution

## Database

Requests are stored in the `requests` table.

Columns:

- `id`
- `session_id`
- `prompt`
- `response`
- `provider_used`
- `original_provider`
- `fallback_used`
- `model_used`
- `latency_ms`
- `request_category`
- `request_status`
- `request_priority`
- `lifecycle_state`
- `queued_at`
- `execution_started_at`
- `completed_at`
- `queue_wait_ms`
- `execution_duration_ms`
- `error_message`
- `created_at`

Lifecycle transitions are stored in `request_lifecycle_events` with:

- `id`
- `request_id`
- `state`
- `detail`
- `created_at`

Operational sessions are stored in `inference_sessions` with:

- `id`
- `title`
- `created_at`
- `updated_at`

Startup applies lightweight schema updates using `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

## Operational Dashboard

The frontend remains HTML/CSS/Vanilla JS and now shows:

- provider used
- original provider
- fallback status
- model used
- request category
- inference latency
- active operational session
- recent session memory
- request ID
- priority
- lifecycle state
- queue wait time
- execution duration
- queue depth
- active executions
- provider capacity
- throughput
- backend request totals
- backend failures
- average backend latency
- fallback usage
- provider health indicators
- request category breakdown

No charting framework is used.

## Manual Backend Run

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

`httpx` is pinned to `0.27.2` for compatibility with the current Groq SDK.

## Manual Frontend Run

```bash
cd frontend
python -m http.server 5500
```

Open:

```text
http://127.0.0.1:5500
```

## Current Scope

Included:

- provider abstraction
- Gemini provider
- Groq provider
- inference service layer
- request classification
- simple provider routing
- simple failover
- operational session memory
- in-memory execution queue
- request prioritization
- scheduler and lifecycle tracking
- provider capacity tracking
- throughput metrics
- provider/model/latency metadata tracking
- request status tracking
- analytics service
- metrics APIs
- Supabase persistence
- operational dashboard
- structured backend logging

Not included:

- authentication
- Redis
- Docker
- Kubernetes
- Kafka
- WebSockets
- advanced routing optimization
- caching
- autoscaling
- React
- Tailwind
