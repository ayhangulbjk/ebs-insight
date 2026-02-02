# EBS-Insight Security Requirements

> **Purpose:** Define security policies, controls, and validation requirements for the EBS-Insight Flask application.
>
> **Scope:** Application security, data protection, SQL injection prevention, prompt injection defense, secrets management, audit trail.
>
> **Last Updated:** 2026-02-02

---

## 1) Security Principles (Hard Guardrails)

These rules MUST NOT be violated under any circumstances:

### 1.1 NO Destructive Operations
- **FORBIDDEN:** DROP, TRUNCATE, DELETE, ALTER, CREATE, INSERT, UPDATE
- **Enforcement:** Parser-level rejection + DB user permission restrictions
- **Exception Process:** Requires explicit user approval + documented rollback plan + audit log entry
- **Violation Response:** Immediate rejection + logging with full context

### 1.2 NO Silent Data Loss
- **FORBIDDEN:** Unlogged truncation, rounding errors, timezone shifts without notice
- **Required:** Explicit marking + structured logging + user notification
- **Measurement:** All data transformations must be measurable and reversible where possible

### 1.3 NO Secrets in Code
- **FORBIDDEN:** Passwords, tokens, DSNs, API keys in source files
- **Required:** Environment variables only (`ORACLE_USER`, `ORACLE_PASS`, `ORACLE_DSN`, etc.)
- **Validation:** Startup config check must fail-fast if secrets are missing
- **Storage:** Use `.env` file (git-ignored) or secure vault for production

### 1.4 NO Uncontrolled SQL Execution
- **FORBIDDEN:** String concatenation in SQL queries
- **FORBIDDEN:** User input directly executed as SQL
- **Required:** Only pre-registered, versioned queries from control catalog
- **Required:** Bind parameters for all dynamic values
- **Validation:** SQL parser must scan for suspicious tokens before execution

### 1.5 NO Uncontrolled Prompt Injection
- **FORBIDDEN:** Mixing user input with system prompts without sanitization
- **Required:** Clear separation between DB results and system instructions
- **Required:** Input sanitization and size limits
- **Required:** Output validation against expected contract

---

## 2) SQL Security (Section 6 - AGENTS.MD)

### 2.1 Read-Only Enforcement

**Database User Configuration:**
- DB user MUST have read-only privileges
- No DML/DDL permissions at database level
- Principle of least privilege

**Application Layer Protection:**
- SQL executor MUST reject non-SELECT statements
- Token-based detection for: INSERT, UPDATE, DELETE, DROP, TRUNCATE, ALTER, CREATE, GRANT, REVOKE
- Case-insensitive pattern matching

**Query Execution Limits:**
- `timeout_seconds` per query (defined in control catalog)
- `row_limit` per query result (defined in control catalog)
- Maximum payload size before Ollama (prevent context overflow)

### 2.2 Bind Parameters (Mandatory)

**Rule:** NEVER concatenate user input into SQL strings.

**Implementation:**
```python
# ✅ CORRECT
cursor.execute("SELECT * FROM table WHERE id = :id", {"id": user_input})

# ❌ WRONG
cursor.execute(f"SELECT * FROM table WHERE id = {user_input}")
```

**Validation:**
- Each control query must declare `binds` array with explicit types
- Executor must validate bind names match declared schema
- Mismatch triggers rejection before execution

### 2.3 Result Sanitization

**Before sending to Ollama:**
1. **Remove/Obfuscate Sensitive Fields:**
   - Usernames, emails, tokens, passwords
   - PII (phone numbers, addresses)
   - Internal system paths, host names

2. **Truncate Large Fields:**
   - Text columns > 500 chars: truncate + add marker
   - CLOB/BLOB: summarize or skip
   - Include row count + "data truncated" flag

3. **Row Limiting:**
   - Apply `row_limit` from control definition
   - If exceeded: include top N + aggregation summary (count, avg, min, max)
   - Add "showing X of Y rows" marker

4. **Safety Classification:**
   - `SAFE_READONLY`: standard sanitization
   - `SENSITIVE`: extra redaction (mask all user identifiers)
   - `HIGH_RISK`: restricted visibility + approval required

---

## 3) Prompt Injection Defense

### 3.1 Input Validation

**User Prompt Sanitization:**
- Maximum length: 2000 characters
- Strip control characters (null bytes, special Unicode)
- Detect and flag injection attempts:
  - System role instructions ("Ignore previous instructions")
  - Prompt leakage attempts ("Print your system prompt")
  - Jailbreak patterns

**Logging:**
- All flagged inputs logged with request_id
- Pattern match score recorded for future analysis

### 3.2 Context Separation

**LLM Prompt Structure (MUST be enforced):**
```
1. System Prompt: Fixed policy + behavior constraints
2. Control Metadata: Catalog entry (title, doc_hint, analysis_prompt)
3. DB Results: Sanitized query outputs (clearly marked)
4. User Question: Original prompt (clearly marked)
```

**Markers Required:**
```
--- START DB RESULTS ---
[sanitized data here]
--- END DB RESULTS ---

--- USER QUESTION ---
[user prompt here]
--- END USER QUESTION ---
```

### 3.3 Output Validation

**LLM Response Contract:**
- Summary (2-5 bullets)
- Health verdict (OK/WARN/CRIT/UNKNOWN)
- Evidence (metrics/rows referenced)
- Optional: Details (compact, capped)
- Optional: Next checks

**Enforcement:**
- Parser validates structure
- Reject responses that don't match contract
- Retry with stricter format instructions (max 1 retry)
- Fallback: return raw metrics + error notice

---

## 4) Secrets Management

### 4.1 Environment Variables (SSOT)

**Required Variables:**
```bash
ORACLE_USER=<db_username>
ORACLE_PASS=<db_password>
ORACLE_DSN=<host:port/service_name>
ORACLE_HOME=/path/to/instantclient
LD_LIBRARY_PATH=$ORACLE_HOME:$LD_LIBRARY_PATH
PATH=$ORACLE_HOME:$PATH
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=ebs-qwen25chat:latest
CATALOG_DIR=/path/to/knowledge/controls
```

**Loading:**
- Use `python-dotenv` or equivalent
- Load from `.env` file (MUST be in `.gitignore`)
- Fail-fast if any required variable is missing

### 4.2 Startup Validation

**Config Validator Must Check:**
1. Oracle thick mode prerequisites (ORACLE_HOME, LD_LIBRARY_PATH, client libs exist)
2. DB credentials present (DO NOT print values)
3. Ollama reachable (ping OLLAMA_URL)
4. Ollama model exists (query /api/tags)
5. Catalog directory exists and is readable
6. Catalog schema validation passes

**Failure Behavior:**
- App MUST refuse to start
- Print clear error message (without exposing secrets)
- Return non-zero exit code

### 4.3 Logging Policy

**FORBIDDEN in logs:**
- Passwords, tokens, API keys
- Full DSN strings (can log host + service name separately)
- Bind parameter values if potentially sensitive (user IDs, account numbers)

**ALLOWED in logs:**
- Request IDs, trace IDs
- User prompts (sanitized)
- Control IDs, query IDs (metadata)
- Execution stats (duration, row counts, error codes)
- Sanitized DB results (after redaction)

---

## 5) Access Control & Audit Trail

### 5.1 Database Access

**Connection Pooling:**
- Use connection pool with limits (max 5 concurrent)
- Close connections explicitly after use
- No long-lived connections

**Session Security:**
- Set `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT` at session level
- Disable client-side result set caching
- Use thick mode (for security features)

### 5.2 Audit Trail (Decision Log)

**Every EBS control request MUST log:**
```json
{
  "request_id": "uuid",
  "timestamp": "ISO8601",
  "user_prompt": "sanitized prompt",
  "intent_classification": "ebs_control | chit_chat | unknown",
  "router_candidates": [
    {
      "control_id": "conc_mgr_status",
      "control_version": "1.0.0",
      "total_score": 0.87,
      "keyword_match_score": 0.9,
      "intent_match_score": 0.95,
      "penalties": []
    }
  ],
  "selected_controls": ["conc_mgr_status"],
  "query_executions": [
    {
      "query_id": "q1",
      "sql_hash": "sha256_of_sql",
      "bind_names": ["status", "tier"],
      "bind_values_redacted": true,
      "duration_ms": 123,
      "rows_returned": 45,
      "rows_truncated": false,
      "error_code": null
    }
  ],
  "ollama_call": {
    "duration_ms": 456,
    "input_tokens_approx": 1200,
    "output_tokens_approx": 300
  },
  "health_verdict": "OK | WARN | CRIT | UNKNOWN",
  "truncation_events": 0
}
```

**Retention:**
- Keep audit logs for minimum 90 days
- Rotate daily
- Compress after 7 days

### 5.3 Rate Limiting

**Per User/Session:**
- Max 10 requests per minute
- Max 100 requests per hour
- Blocked users logged with request_id

**Purpose:**
- Prevent DB overload
- Prevent Ollama overload
- Detect abuse patterns

---

## 6) Control Catalog Security

### 6.1 Schema Validation

**Startup Validation:**
- All control files must pass JSON schema validation
- Missing required fields → reject control
- Invalid query syntax → reject control

**Required Fields (Security-Relevant):**
- `control_id`, `version`
- `intent` (classification)
- `keywords` (for routing)
- `queries[].sql` (explicit SQL text or reference)
- `queries[].binds` (explicit bind parameter declarations)
- `queries[].row_limit`, `queries[].timeout_seconds`
- `safety_classification` (SAFE_READONLY | SENSITIVE | HIGH_RISK)

### 6.2 Query Versioning

**Rule:** Any SQL change requires version bump.

**Tracking:**
- Control version (semver: 1.0.0 → 1.1.0)
- Change note in catalog entry
- Expected `result_schema` updated if columns change

**Audit:**
- Query hash (SHA256 of normalized SQL) logged per execution
- Enables detection of unauthorized query modifications

### 6.3 Safety Classification

**SAFE_READONLY:**
- Default for diagnostic queries
- Standard sanitization rules
- No additional approval needed

**SENSITIVE:**
- Contains user data or potential PII
- Extra redaction (mask usernames, emails, IDs)
- Logged with sensitivity flag

**HIGH_RISK:**
- Could reveal operational secrets (passwords, keys, internal configs)
- Restricted visibility (admin approval required)
- Extra audit trail

---

## 7) Error Handling (Secure Disclosure)

### 7.1 User-Facing Errors

**FORBIDDEN:**
- Stack traces
- SQL text
- Bind parameter values
- Internal file paths
- Database connection details

**ALLOWED:**
- Generic error message ("Database temporarily unavailable")
- Request ID for support reference
- Suggested next action ("Please try again later")

### 7.2 Internal Error Logging

**Required Context:**
- Full stack trace
- Request ID
- User prompt (sanitized)
- Control ID + query ID
- SQL hash (not full SQL text)
- Error code + message from DB/Ollama
- Timestamp

### 7.3 Fallback Behavior

**DB Connection Failure:**
- Return short message + request ID
- DO NOT retry indefinitely (max 3 retries with backoff)
- Log failure with diagnostic info

**Ollama Failure:**
- Return fallback summary of raw metrics (if DB results exist)
- Log failure with request ID
- Notify user: "Summary generation unavailable, showing raw data"

**Router Failure:**
- Refuse to execute queries
- Ask user to rephrase or pick a category
- Provide examples of valid prompts

---

## 8) Testing Requirements

### 8.1 Security Unit Tests (MANDATORY)

**Must Include:**
1. **SQL Injection Tests:**
   - Attempt to execute DROP, DELETE, ALTER via bind parameters
   - Attempt to execute multiple statements (SQL injection)
   - Attempt to bypass validation with comments, encoding

2. **Sanitization Tests:**
   - Verify PII redaction (emails, usernames, tokens)
   - Verify truncation behavior (large text, many rows)
   - Verify safety classification enforcement

3. **Prompt Injection Tests:**
   - Attempt to override system prompt
   - Attempt to leak system prompt
   - Attempt jailbreak patterns
   - Verify context separation markers

4. **Secrets Leakage Tests:**
   - Scan logs for password patterns
   - Scan error messages for DSN strings
   - Verify env var usage (no hardcoded secrets)

### 8.2 Integration Tests

**Smoke Tests:**
1. DB connectivity + single SAFE_READONLY control execution
2. Ollama connectivity + canned prompt → validate output contract
3. Catalog loading + schema validation

**Failure Tests:**
1. Missing env vars → app refuses to start
2. Invalid SQL in catalog → control rejected at load time
3. Timeout exceeded → query cancelled + logged
4. Row limit exceeded → truncation + summary applied

---

## 9) Operational Security

### 9.1 Default Safety

**Single Control Default:**
- Run ONE control per prompt unless user explicitly asks for detailed analysis
- Reduces DB load + Ollama cost

**Health Bundle:**
- For wide prompts ("sistem sağlıklı mı?"), run predefined health bundle
- Bundle must be explicitly listed and versioned in catalog
- Bundle limited to SAFE_READONLY controls only

### 9.2 Monitoring & Alerts

**Security Metrics:**
- `sql_injection_attempts_total` (rejected queries)
- `prompt_injection_flags_total` (flagged inputs)
- `rate_limit_violations_total`
- `sensitive_data_access_total` (SENSITIVE/HIGH_RISK controls)

**Alerting:**
- Spike in injection attempts → investigate user session
- Repeated rate limit violations → consider blocking
- HIGH_RISK control access → notify admin

---

## 10) Security Checklist (Pre-Deployment)

Before deploying to production, verify:

- [ ] All secrets moved to environment variables (no hardcoded values)
- [ ] `.env` file added to `.gitignore`
- [ ] Startup config validation implemented and tested
- [ ] DB user has read-only permissions (verified in DB)
- [ ] SQL parser rejects DML/DDL (tested with injection attempts)
- [ ] Bind parameters used for all dynamic values (code review)
- [ ] Result sanitization implemented (PII redaction tested)
- [ ] Prompt injection defense implemented (markers + validation)
- [ ] LLM output contract enforced (parser + validation)
- [ ] Audit trail logging implemented (decision log + metrics)
- [ ] Error handling does not leak secrets (tested)
- [ ] Rate limiting configured (per user/session)
- [ ] Security unit tests passing (SQL injection, sanitization, prompt injection)
- [ ] Integration smoke tests passing (DB, Ollama, catalog)
- [ ] Logs reviewed for secret leakage (grep for password patterns)
- [ ] Control catalog schema validated (all controls pass)
- [ ] Safety classifications assigned (all controls)
- [ ] Query versioning enforced (version bumps documented)

---

## 11) Incident Response

### 11.1 Security Incident Definition

**Triggers:**
- Confirmed SQL injection attempt (bypassed validation)
- Confirmed prompt injection (leaked system prompt or executed malicious code)
- Secret leaked in logs or error messages
- Unauthorized data access (privilege escalation)

### 11.2 Response Procedure

1. **Immediate:** Isolate affected component (stop queries, disable control, block user)
2. **Assess:** Review audit logs, identify scope (what data accessed, how)
3. **Remediate:** Patch vulnerability, rotate secrets if needed
4. **Document:** Write incident report (what, when, how, impact, fix)
5. **Learn:** Update security tests, add validation rules, improve monitoring

---

## 12) References

- **AGENTS.MD:** Primary source for security rules (Section 0.3, 6, 7, 13)
- **OWASP Top 10:** SQL Injection, Prompt Injection, Secrets Management
- **Oracle Security Best Practices:** Read-only users, least privilege
- **Python Security:** Input validation, safe SQL execution (python-oracledb)
- **LLM Security:** Prompt injection defense, output validation

---

**END OF SECURITY.MD**
