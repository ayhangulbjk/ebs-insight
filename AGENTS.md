## AGENTS.MD — EBS-Insight (Flask + Ollama) Rules

> Purpose: Establish a single source of truth for how humans + AI collaborate to design, modify, and operate a production-grade **Flask chat application** that uses **Ollama** to select and run **Oracle EBS R12** diagnostic controls, then summarizes results.
>
> Scope: Python 3.x, Flask, python-oracledb (thick mode), Oracle EBS R12.2 DB read-only diagnostics, Ollama (local), YAML/MD control catalog.
>
> Non-Goal: This is not a tutorial, framework comparison, or generic style guide.

---

## 0) Operation Mode (MANDATORY)

### 0.1 Code Generation Policy

- ALWAYS plan first, generate second.
- Every change MUST start with a **Change Declaration** block containing:
  - **Intent** — short, explicit statement of the problem being solved.
  - **Impact** — explicit list of affected endpoints, DB objects, control catalog entries, prompt routing rules, and any backwards-incompatible effects.
  - **Files to change** — explicit file paths with action (add / modify / remove) for each entry.
- Code without an approved plan is invalid output.

### 0.2 Small Batch Rule

- Generate maximum **3 files per batch** if strongly coupled.
- Do NOT proceed to the next batch without explicit approval.
- Every generated file MUST include:
  - clear responsibility
  - minimal public surface
  - comments only where intent is non-obvious

### 0.3 Hard Guardrails (AI MUST NOT VIOLATE)

- **NO destructive operations by default**
  - DROP, TRUNCATE, DELETE, ALTER are FORBIDDEN
  - Allowed only with:
    - explicit user approval
    - clearly documented rollback plan
- **NO silent data loss**
  - truncation, rounding, timezone shifts
  - MUST be explicit, logged, and measurable
- **NO secrets in code**
  - No passwords, tokens, DSNs, keys in source
  - Use env vars / runtime injection only
- **NO uncontrolled SQL execution**
  - User text MUST NOT be executed as SQL.
  - Only allow **pre-registered, versioned queries** from the control catalog.
- **NO uncontrolled prompt injection**
  - DB results and system prompts must be separated.
  - Inputs must be sanitized and size-limited.

---

## 1) Runtime SSOT (ENV + PROCESS)

### 1.1 Runtime Environment (SSOT)

All runtime configuration MUST be provided by environment variables (e.g., `.env`), never hardcoded:

- `ORACLE_USER='**'`
- `ORACLE_PASS='**'`
- `ORACLE_DSN='**'`
- `HOME="/appl01"`
- `ORACLE_HOME=/appl01/ebs-insight/instantclient_21_1`
- `LD_LIBRARY_PATH=$ORACLE_HOME:$LD_LIBRARY_PATH`
- `PATH=$ORACLE_HOME:$PATH`
- `OLLAMA_URL=http://127.0.0.1:11434`
- `OLLAMA_MODEL=ebs-qwen25chat:latest`
- `CATALOG_DIR=/appl01/ebs-insight/knowledge/controls`

### 1.2 Fail-Fast Config Validation (Mandatory)

On startup the app MUST validate:
- Oracle thick mode prerequisites (`ORACLE_HOME`, `LD_LIBRARY_PATH`, client libs)
- DB credentials present (not printed)
- Ollama reachable (`OLLAMA_URL`) and model name configured
- Catalog directory exists and loads successfully
If any validation fails → app must refuse to start with a clear error.

---

## 2) System Goal (What We Are Building)

We are building a Flask-based chat application where:

1) User sends a prompt (e.g., “şu an ebs’te concurrent manager durumu nedir?”)  
2) App classifies the prompt:
   - **Chit-chat** → short generic response (no DB)
   - **EBS control request** → route to the correct control(s)
3) App selects control queries via a **score-based router**, executes queries against EBS DB (read-only), collects results.
4) App calls **Ollama** with:
   - system policy + control metadata + retrieved DB results (sanitized)
5) Ollama returns:
   - concise summary + key observations + (optional) a compact detail section
6) App logs the decision trail (scores, candidates, reason codes) for auditing.

---

## 3) Architecture SSOT (APP FLOW)

### 3.1 Mandatory Layering

**Web (Flask)**
- Auth/session (if any), request parsing, response shaping
- No DB logic besides calling service interfaces

**Routing / Intent**
- Detect: chit-chat vs EBS-control vs unknown
- Candidate control retrieval and scoring
- Explainable routing output (why selected)

**Controls Catalog (SSOT)**
- Versioned control definitions in `CATALOG_DIR`
- Each control defines:
  - id, name, tags
  - keywords (TR+EN variations)
  - query references
  - safety classification
  - summarization instructions (analysis_prompt)

**DB Access**
- Read-only connections
- Parameter binding only
- Query execution + result shaping with size limits

**LLM Adapter (Ollama)**
- Prompt templates (system + user)
- Output parsing + response policy enforcement

**Observability**
- Structured logs, metrics, trace IDs
- Decision audit trail for routing/scoring

❌ Skipping layers is not allowed.

---

## 4) Control Catalog Rules (Non-Negotiable)

### 4.1 Control Definition Contract (Mandatory)

Every control MUST have:
- `control_id` (stable, unique)
- `version` (semver or date-based)
- `title` + `description`
- `intent` (diagnostic domain, e.g., conc_mgr / workflow / adop / invalid_objects)
- `keywords` (TR + EN; include synonyms, common misspellings)
- `queries[]` (1..N), each:
  - `query_id`
  - `sql` (or reference to sql file)
  - `binds` (explicit bind names + types)
  - `row_limit` and `timeout_seconds`
  - `result_schema` (expected columns, types)
- `doc_hint` (what to look for)
- `analysis_prompt` (how LLM should interpret)

If any mandatory field is missing → DO NOT PROCEED.

### 4.2 Query Versioning

- Queries MUST be explicit and versioned.
- Any query change requires:
  - bumping control version
  - recording a change note
  - updating expected result_schema if needed

### 4.3 Safety Classification

Each control MUST declare one:
- `SAFE_READONLY` (default)
- `SENSITIVE` (contains user data / potential PII → extra redaction)
- `HIGH_RISK` (still read-only but could reveal operational secrets → restricted visibility)

---

## 5) Score-Based Routing (Mandatory)

### 5.1 Router Output Must Be Explainable

For every EBS-control prompt, router MUST produce a decision object that includes:
- prompt intent (classification)
- top-N candidate controls
- per-candidate score breakdown:
  - keyword_match_score
  - intent_match_score
  - sql_shape_score (if used)
  - recency/priority boost (if used)
  - penalties (ambiguity, chit-chat indicators, unsafe indicators)
- selected controls + justification text

This decision object MUST be logged (sanitized).

### 5.2 Deterministic Tie-Breaking

If scores are close:
- prefer controls with higher intent match
- then higher keyword confidence
- then fewer queries (simpler)
- then stable priority order defined in catalog
No randomness in production routing.

### 5.3 Ambiguity Handling

If router confidence is below threshold:
- DO NOT guess silently.
- Return a clarification question OR present top 3 interpretations.
- Provide examples of acceptable user phrasing (TR+EN).

---

## 6) SQL Execution Rules (Hard Security)

### 6.1 Read-Only Enforcement

- DB user should be least privilege, read-only.
- Execution layer MUST reject:
  - any non-SELECT statements
  - statements containing suspicious tokens (DDL/DML)
- Use bind parameters only (no string concatenation).
- Apply:
  - timeout per query
  - row limit
  - max payload size

### 6.2 Result Shaping & Sanitization

Before sending to Ollama:
- remove/obfuscate sensitive fields (usernames, emails, tokens)
- truncate large text fields
- cap rows (e.g., top 50) + include aggregation summary
- include “data truncated” marker when applicable

---

## 7) Ollama Prompting Rules (Policy + Templates)

### 7.1 System Prompt Policy (Mandatory)

Ollama MUST be instructed that:
- It is an **Oracle EBS R12.2 operations assistant**
- It MUST summarize based on provided DB results only
- It MUST NOT invent DB data
- If data is missing/inconclusive → say so and propose next control(s)
- It MUST interpet and explain what is happening based on given data.

### 7.2 Prompt Structure (Stable)

Every LLM call MUST include:
1) **System**: policy + behavior constraints
2) **Context**: control metadata (title, doc_hint, expected signals)
3) **Data**: sanitized query results + aggregates + execution meta
4) **User question**: original prompt

### 7.3 Output Contract (Mandatory)

LLM output MUST follow:
- **Summary (2–5 bullets)**
- **Health/Status verdict** (e.g., OK / WARN / CRIT / UNKNOWN)
- **Evidence** (key metrics/rows referenced)
- **Details** (optional, compact; capped)
- **Next checks** (optional; only if confidence is low)

If output deviates, app must either:
- re-ask with a stricter format prompt, OR
- post-process into the contract (without changing meaning)

---

## 8) Observability (Required)

### 8.1 Structured Logging (JSON)

Every request MUST log:
- request_id / trace_id
- user prompt (sanitized)
- intent classification
- router candidates + scores
- selected control ids + versions
- query execution stats (duration, rows, truncated, error code)
- ollama call duration + token-ish size estimates (approx)
- final status verdict (OK/WARN/CRIT/UNKNOWN)

### 8.2 Metrics (Minimum)

- requests_total
- ebs_control_requests_total
- routing_confidence_histogram
- db_query_duration_seconds
- db_query_errors_total (by code)
- ollama_duration_seconds
- response_size_bytes
- truncation_events_total

### 8.3 Audit Trail

Decision trail MUST be reproducible:
- catalog version used
- control versions selected
- sql hash (of executed SQL text)
- bind names (values redacted)
- result row counts + truncation flags

---

## 9) Error Handling Rules (Production Behavior)

- DB connection failures must return:
  - short user message
  - diagnostic reference id (request_id)
  - no secret leakage
- Ollama failures must:
  - return a fallback summary of raw metrics (if any)
  - log the failure with request_id
- Router failures must:
  - refuse to run queries
  - ask user to rephrase or pick a category

---

## 10) Testing Standard

### 10.1 Unit Tests (Mandatory)

- Router scoring functions: deterministic tests
- Sanitization/redaction: golden test cases
- Output contract parser/validator
- **NEVER** run application in this environment. Because `.env` file is not configured in this environment. Instead of running the application, you MUST test changes with manual scripts.

### 10.2 Integration Smoke Tests

- DB connectivity + a single SAFE_READONLY control
- Ollama connectivity + a canned prompt
- Catalog loading + schema validation

❌ Changes to routing or sanitization without tests are invalid.

---

## 11) Operational Safety Defaults

- Default to running **one control** unless user asks “detaylı analiz”.
- For “wide” prompts (e.g., “sistem sağlıklı mı?”):
  - run a predefined minimal “health bundle” of SAFE_READONLY controls
  - bundle must be explicitly listed and versioned in catalog
- Rate-limit per session/user (to protect DB and Ollama).

---

## 12) AI Pull Request Checklist (Must Pass)

Before proposing completion, AI MUST verify:
- Startup config validation exists and fails fast
- Catalog schema validation exists
- Router decision is explainable and logged
- SQL execution is read-only enforced + parameterized
- Sanitization/redaction is applied before LLM
- LLM prompt + output contract enforced
- Metrics/logs present; no secrets logged
- Tests added/updated for routing/sanitization/output contract

---

### 13) DB session rule (Mandatory)

All knowledge/control SQL queries MUST be non-disruptive read-only operations.

**Hard enforcement:**
- Execution layer MUST reject any DML (INSERT, UPDATE, DELETE) or DDL (CREATE, ALTER, DROP, TRUNCATE) statements
- Parser must scan query text for suspicious tokens before execution

**Violation handling:**
- Log attempt with full context (query hash, user session, timestamp, request_id)
- Return error to user without exposing query details

## FINAL RULE

If any rule above cannot be met, the AI MUST stop and ask.
Silent assumptions are considered a failure.
