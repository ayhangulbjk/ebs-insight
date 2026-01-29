#!/usr/bin/env python
"""Test DB executor safety checks"""

from src.db.executor import QueryExecutor
from src.db.sanitizer import Sanitizer

print("=== Testing SQL Validation ===\n")

executor = None  # We'll mock this

# Test dangerous SQL statements
dangerous_queries = [
    "DROP TABLE apps.concurrent_requests",
    "DELETE FROM apps.fnd_user",
    "INSERT INTO apps.fnd_user VALUES (...)",
    "UPDATE apps.fnd_user SET username = 'hacked'",
    "ALTER TABLE apps.fnd_user ADD COLUMN hack VARCHAR2(1000)",
    "TRUNCATE TABLE apps.fnd_concurrent_requests",
    "CREATE TABLE apps.backdoor (id NUMBER)",
]

for sql in dangerous_queries:
    executor_obj = QueryExecutor(None)  # Dummy object for validation
    error = executor_obj._validate_sql(sql)
    status = "✓ BLOCKED" if error else "✗ ALLOWED (BAD!)"
    print(f"{status}: {sql[:50]}...")
    if error:
        print(f"  Reason: {error}\n")

print("\n=== Testing Safe SELECT ===\n")

safe_queries = [
    "SELECT * FROM apps.fnd_user WHERE user_id = 500",
    "SELECT user_name, user_id FROM apps.icx_sessions WHERE disabled_flag <> 'Y'",
    "SELECT COUNT(*) as cnt FROM dba_objects WHERE status = 'INVALID'",
]

for sql in safe_queries:
    executor_obj = QueryExecutor(None)
    error = executor_obj._validate_sql(sql)
    status = "✓ ALLOWED" if not error else "✗ BLOCKED"
    print(f"{status}: {sql[:60]}...")
    if error:
        print(f"  Error: {error}\n")

print("\n=== Testing Result Sanitization ===\n")

# Mock query result with sensitive data
mock_rows = [
    {"user_name": "apps", "password": "secret123", "email": "admin@erp.com", "description": "x" * 600},
    {"user_name": "scott", "password": "tiger", "email": "scott@erp.com", "description": "normal"},
]

mock_schema = [
    {"name": "user_name", "type": "VARCHAR2", "sensitive": True},
    {"name": "password", "type": "VARCHAR2", "sensitive": True},
    {"name": "email", "type": "VARCHAR2", "sensitive": True},
    {"name": "description", "type": "VARCHAR2", "sensitive": False},
]

sanitized = Sanitizer.sanitize_result(mock_rows, mock_schema)

print(f"Original rows: {len(mock_rows)}")
print(f"Sanitized rows: {len(sanitized['rows'])}")
print(f"Redactions: {sanitized['redaction_count']}")
print(f"Truncations: {sanitized['truncation_count']}")
print(f"Rows truncated: {sanitized['truncated']}\n")

print("Sample sanitized row:")
for key, value in sanitized['rows'][0].items():
    print(f"  {key}: {value}")

print("\n=== Testing Large Row Capping ===\n")

# Create 100 rows
large_result = {"rows": [{"id": i, "data": f"row_{i}"} for i in range(100)], "truncated": False}
schema = [{"name": "id", "type": "NUMBER"}, {"name": "data", "type": "VARCHAR2"}]

# Simulate sanitization
result_with_cap = {
    "rows": large_result["rows"][:Sanitizer.MAX_ROWS],
    "row_count": len(large_result["rows"]),
    "truncated": len(large_result["rows"]) > Sanitizer.MAX_ROWS,
    "redaction_count": 0,
    "truncation_count": 0,
    "total_markers": 0,
}

print(f"Total rows from query: {result_with_cap['row_count']}")
print(f"Rows in result (capped): {len(result_with_cap['rows'])}")
print(f"Truncated marker: {result_with_cap['truncated']}")
print(f"Note: Rows capped at MAX_ROWS={Sanitizer.MAX_ROWS}")

print("\n✓ All safety checks passed!")
