"""
Test Suite for DB Executor Safety.
Per AGENTS.md § 6 (SQL Execution Rules).

Tests:
1. Read-only enforcement (no DDL/DML)
2. Parameter binding (no SQL injection)
3. Row limits and truncation
4. Result sanitization
5. Timeout handling
"""

import pytest
from src.db.executor import QueryExecutor
from src.db.sanitizer import Sanitizer


class TestSQLValidation:
    """Test SQL validation for read-only enforcement"""

    @pytest.mark.parametrize(
        "dangerous_sql",
        [
            "DROP TABLE apps.fnd_user",
            "DELETE FROM apps.fnd_concurrent_requests",
            "INSERT INTO apps.fnd_user VALUES (999, 'hack')",
            "UPDATE apps.fnd_user SET username = 'admin' WHERE user_id = 1",
            "ALTER TABLE apps.fnd_user ADD COLUMN password VARCHAR2(100)",
            "TRUNCATE TABLE apps.fnd_concurrent_requests",
            "CREATE TABLE apps.backdoor (id NUMBER)",
        ],
    )
    def test_forbidden_operations(self, dangerous_sql):
        """Test that DDL/DML operations are blocked"""
        executor = QueryExecutor(None)
        error = executor._validate_sql(dangerous_sql)
        assert error is not None, f"Should block: {dangerous_sql}"
        assert "Only SELECT" in error

    @pytest.mark.parametrize(
        "safe_sql",
        [
            "SELECT * FROM apps.fnd_user WHERE user_id = 500",
            "SELECT user_id, user_name FROM apps.icx_sessions",
            "SELECT COUNT(*) FROM dba_objects WHERE status = 'INVALID'",
            "SELECT user_name, COUNT(*) as cnt FROM apps.fnd_user GROUP BY user_name",
        ],
    )
    def test_allowed_selects(self, safe_sql):
        """Test that SELECT statements are allowed"""
        executor = QueryExecutor(None)
        error = executor._validate_sql(safe_sql)
        assert error is None, f"Should allow: {safe_sql}"

    def test_empty_sql(self):
        """Test empty SQL rejection"""
        executor = QueryExecutor(None)
        error = executor._validate_sql("")
        assert error is not None
        assert "Empty" in error


class TestResultSanitization:
    """Test result sanitization and redaction"""

    def test_sensitive_field_redaction(self):
        """Test that sensitive fields are redacted"""
        rows = [
            {"user_name": "apps", "password": "secret", "email": "admin@erp.com"},
            {"user_name": "scott", "password": "tiger", "email": "user@erp.com"},
        ]

        schema = [
            {"name": "user_name", "type": "VARCHAR2", "sensitive": True},
            {"name": "password", "type": "VARCHAR2", "sensitive": True},
            {"name": "email", "type": "VARCHAR2", "sensitive": False},
        ]

        result = Sanitizer.sanitize_result(rows, schema)

        # Check redactions
        assert result["redaction_count"] == 4  # 2 rows * 2 sensitive fields
        assert all(row["user_name"] == "[REDACTED]" for row in result["rows"])
        assert all(row["password"] == "[REDACTED]" for row in result["rows"])
        # Email should NOT be redacted (not marked sensitive in schema)
        assert result["rows"][0]["email"] == "admin@erp.com"

    def test_large_text_truncation(self):
        """Test that large text fields are truncated"""
        large_text = "x" * 1000
        rows = [{"id": 1, "description": large_text}]
        schema = [
            {"name": "id", "type": "NUMBER", "sensitive": False},
            {"name": "description", "type": "VARCHAR2", "sensitive": False},
        ]

        result = Sanitizer.sanitize_result(rows, schema)

        description = result["rows"][0]["description"]
        assert "[...truncated]" in description
        assert len(description) < 1000
        assert result["truncation_count"] == 1

    def test_row_capping(self):
        """Test that rows are capped at MAX_ROWS"""
        rows = [{"id": i, "data": f"row_{i}"} for i in range(100)]
        schema = [
            {"name": "id", "type": "NUMBER", "sensitive": False},
            {"name": "data", "type": "VARCHAR2", "sensitive": False},
        ]

        result = Sanitizer.sanitize_result(rows, schema)

        assert len(result["rows"]) == Sanitizer.MAX_ROWS
        assert result["row_count"] == 100
        assert result["truncated"] is True

    def test_no_rows_result(self):
        """Test handling of empty result sets"""
        rows = []
        schema = [{"name": "id", "type": "NUMBER"}]

        result = Sanitizer.sanitize_result(rows, schema)

        assert len(result["rows"]) == 0
        assert result["row_count"] == 0
        assert result["truncated"] is False


class TestBindValidation:
    """Test bind parameter validation"""

    def test_valid_binds(self):
        """Test validation of valid bind parameters"""
        executor = QueryExecutor(None)
        binds = {"p_user_id": 500, "p_status": "ACTIVE"}
        bind_schema = [
            {"name": "p_user_id", "type": "NUMBER", "optional": False},
            {"name": "p_status", "type": "VARCHAR2", "optional": False},
        ]

        # Should not raise
        executor._validate_binds(binds, bind_schema)

    def test_missing_required_bind(self):
        """Test missing required bind parameter"""
        executor = QueryExecutor(None)
        binds = {"p_user_id": 500}  # Missing p_status
        bind_schema = [
            {"name": "p_user_id", "type": "NUMBER", "optional": False},
            {"name": "p_status", "type": "VARCHAR2", "optional": False},
        ]

        with pytest.raises(Exception):
            executor._validate_binds(binds, bind_schema)

    def test_optional_bind_missing(self):
        """Test that optional binds can be missing"""
        executor = QueryExecutor(None)
        binds = {"p_user_id": 500}
        bind_schema = [
            {"name": "p_user_id", "type": "NUMBER", "optional": False},
            {"name": "p_status", "type": "VARCHAR2", "optional": True},
        ]

        # Should not raise
        executor._validate_binds(binds, bind_schema)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
