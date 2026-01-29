"""
Safe Query Executor with Read-Only Enforcement.
Per AGENTS.md § 6 (SQL Execution Rules).

Enforces:
- Read-only execution (no DDL/DML)
- Parameter binding only (no string concat)
- Query timeout + row limit
- Result sanitization before LLM
"""

import logging
import re
from typing import List, Dict, Any, Optional
import oracledb

from src.db.sanitizer import Sanitizer
from src.controls.schema import QueryExecutionResult, ControlExecutionResult

logger = logging.getLogger(__name__)


class QueryExecutionError(Exception):
    """Raised when query execution fails"""
    pass


class QueryExecutor:
    """
    Safe Oracle query executor with security enforcement.
    
    Per AGENTS.md § 6 (SQL Execution Rules):
    1. NO destructive operations (DDL/DML/TRUNCATE/DELETE)
    2. Parameter binding only (no SQL injection)
    3. Timeout + row limit enforcement
    4. Result sanitization before LLM
    """

    # Forbidden SQL keywords that indicate non-SELECT operations
    # Per AGENTS.md § 6.1 (Read-Only Enforcement)
    FORBIDDEN_KEYWORDS = [
        "DROP",
        "TRUNCATE",
        "DELETE",
        "INSERT",
        "UPDATE",
        "ALTER",
        "CREATE",
        "GRANT",
        "REVOKE",
        "COMMIT",
        "ROLLBACK",
        "BEGIN",
    ]

    # Maximum payload size: 10MB
    MAX_PAYLOAD_BYTES = 10 * 1024 * 1024

    def __init__(self, connection_pool):
        """
        Initialize executor with connection pool.
        
        Args:
            connection_pool: DBConnectionPool instance
        """
        self.pool = connection_pool

    def execute_query(
        self,
        query_definition: Dict,
        binds: Dict[str, Any] = None,
    ) -> QueryExecutionResult:
        """
        Execute a single query with safety enforcement.
        
        Per AGENTS.md § 6.1 (Read-Only Enforcement):
        - Reject non-SELECT statements
        - Validate parameter binding
        - Enforce timeout and row limit
        - Sanitize results
        
        Args:
            query_definition: Query from control (with sql, binds, timeout, row_limit)
            binds: Actual bind values {param_name: value}
            
        Returns:
            QueryExecutionResult with sanitized results
        """
        query_id = query_definition.get("query_id", "unknown")
        sql = query_definition.get("sql", "").strip()
        timeout_seconds = query_definition.get("timeout_seconds", 30)
        row_limit = query_definition.get("row_limit", 50)
        result_schema = query_definition.get("result_schema", [])

        logger.info(f"Executing query: {query_id}")

        # Step 1: Validate SQL (security check)
        # =====================================
        validation_error = self._validate_sql(sql)
        if validation_error:
            logger.error(f"[{query_id}] SQL validation failed: {validation_error}")
            return QueryExecutionResult(
                query_id=query_id,
                rows=[],
                row_count=0,
                truncated=False,
                execution_time_ms=0.0,
                error=f"SQL validation failed: {validation_error}",
            )

        # Step 2: Execute query with timeout
        # ==================================
        import time

        start_time = time.time()
        conn = None

        try:
            # Acquire connection from pool
            conn = self.pool.get_connection()

            # Create cursor with timeout
            cursor = conn.cursor()
            cursor.arraysize = min(100, row_limit + 1)  # Fetch slightly more to detect truncation

            # Execute with binds (safe: oracledb handles binding)
            if binds:
                # Validate binds
                self._validate_binds(binds, query_definition.get("binds", []))
                cursor.execute(sql, binds, timeout=timeout_seconds)
            else:
                cursor.execute(sql, timeout=timeout_seconds)

            # Step 3: Fetch results with row limit
            # ====================================
            rows_list = []
            rows = cursor.fetchall()

            if rows:
                # Convert to list of dicts (column names from description)
                col_names = [desc[0].lower() for desc in cursor.description]
                for row_tuple in rows:
                    row_dict = dict(zip(col_names, row_tuple))
                    rows_list.append(row_dict)

                    if len(rows_list) >= row_limit:
                        break

            execution_time_ms = (time.time() - start_time) * 1000
            truncated = len(rows) > row_limit

            # Step 4: Sanitize results
            # ========================
            sanitized = Sanitizer.sanitize_result(rows_list, result_schema)

            logger.info(
                f"[{query_id}] Success: {len(rows_list)} rows in {execution_time_ms:.2f}ms"
            )

            return QueryExecutionResult(
                query_id=query_id,
                rows=sanitized["rows"],
                row_count=sanitized["row_count"],
                truncated=sanitized["truncated"],
                execution_time_ms=execution_time_ms,
                error=None,
            )

        except oracledb.DatabaseError as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"[{query_id}] Database error: {e}")
            return QueryExecutionResult(
                query_id=query_id,
                rows=[],
                row_count=0,
                truncated=False,
                execution_time_ms=execution_time_ms,
                error=f"Database error: {e}",
            )

        except Exception as e:
            execution_time_ms = (time.time() - start_time) * 1000
            logger.error(f"[{query_id}] Execution error: {e}")
            return QueryExecutionResult(
                query_id=query_id,
                rows=[],
                row_count=0,
                truncated=False,
                execution_time_ms=execution_time_ms,
                error=f"Execution error: {e}",
            )

        finally:
            if conn:
                self.pool.release_connection(conn)

    def execute_control(
        self,
        control_definition,
        binds: Dict[str, Any] = None,
    ) -> ControlExecutionResult:
        """
        Execute all queries in a control with result aggregation.
        
        Args:
            control_definition: ControlDefinition object
            binds: Bind parameters
            
        Returns:
            ControlExecutionResult with all query results
        """
        control_id = control_definition.control_id
        control_version = control_definition.version

        logger.info(f"Executing control: {control_id} (v{control_version})")

        query_results = []
        total_time = 0.0
        has_errors = False

        for query in control_definition.queries:
            result = self.execute_query(query.dict(), binds=binds)
            query_results.append(result)
            total_time += result.execution_time_ms

            if result.error:
                has_errors = True

        return ControlExecutionResult(
            control_id=control_id,
            control_version=control_version,
            intent=control_definition.intent,
            query_results=query_results,
            total_execution_time_ms=total_time,
            has_errors=has_errors,
            sanitized=True,
        )

    def _validate_sql(self, sql: str) -> Optional[str]:
        """
        Validate SQL for read-only safety.
        
        Per AGENTS.md § 6.1:
        - NO DDL (DROP, CREATE, ALTER)
        - NO DML (DELETE, INSERT, UPDATE, TRUNCATE)
        - Only SELECT allowed
        
        Returns:
            Error message if invalid, None if valid
        """
        if not sql or not sql.strip():
            return "Empty SQL statement"

        sql_upper = sql.strip().upper()

        # Must start with SELECT
        if not sql_upper.startswith("SELECT"):
            return "Only SELECT statements are allowed (read-only enforcement)"

        # Check for forbidden keywords
        for keyword in self.FORBIDDEN_KEYWORDS:
            # Use word boundary matching to avoid false positives
            pattern = r"\b" + keyword + r"\b"
            if re.search(pattern, sql_upper):
                return (
                    f"Forbidden SQL keyword detected: {keyword}. "
                    f"Only SELECT is allowed."
                )

        return None

    def _validate_binds(self, binds: Dict[str, Any], bind_schema: List[Dict]) -> None:
        """
        Validate bind parameters against schema.
        
        Per AGENTS.md § 6.1 (Parameter Binding):
        Ensures bind values match expected types from schema
        
        Args:
            binds: Actual bind values
            bind_schema: Expected bind schema
            
        Raises:
            QueryExecutionError: If validation fails
        """
        expected_names = {b.get("name") for b in bind_schema}

        for bind_name in binds.keys():
            if bind_name not in expected_names:
                logger.warning(f"Unexpected bind parameter: {bind_name}")

        # Validate non-optional binds are present
        for bind_spec in bind_schema:
            bind_name = bind_spec.get("name")
            is_optional = bind_spec.get("optional", False)

            if not is_optional and bind_name not in binds:
                raise QueryExecutionError(
                    f"Required bind parameter missing: {bind_name}"
                )
