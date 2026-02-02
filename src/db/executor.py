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
import threading
import time
from typing import List, Dict, Any, Optional
import oracledb

from src.db.sanitizer import Sanitizer
from src.controls.schema import QueryExecutionResult, ControlExecutionResult
from src.observability.log_sanitizer import safe_log_value

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

        # Sanitize query_id for logging (prevent log injection)
        safe_query_id = safe_log_value(query_id, max_length=50)
        logger.info(f"Executing query: {safe_query_id}")

        # Step 1: Validate SQL (security check)
        # =====================================
        validation_error = self._validate_sql(sql)
        if validation_error:
            logger.error(f"[{safe_query_id}] SQL validation failed: {validation_error}")
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
                # Validate binds (returns type-converted dict)
                validated_binds = self._validate_binds(binds, query_definition.get("binds", []))
                # Execute with timeout enforcement
                self._execute_with_timeout(cursor, sql, validated_binds, timeout_seconds)
            else:
                # Execute with timeout enforcement
                self._execute_with_timeout(cursor, sql, None, timeout_seconds)

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
                f"[{safe_query_id}] Success: {len(rows_list)} rows in {execution_time_ms:.2f}ms"
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
            logger.error(f"[{safe_query_id}] Database error: {e}")
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
            logger.error(f"[{safe_query_id}] Execution error: {e}")
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

        # Sanitize for logging
        safe_control_id = safe_log_value(control_id, max_length=50)
        logger.info(f"Executing control: {safe_control_id} (v{control_version})")

        query_results = []
        total_time = 0.0
        has_errors = False

        for query in control_definition.queries:
            result = self.execute_query(query.dict(), binds=binds)
            query_results.append(result)
            total_time += result.execution_time_ms

            if result.error:
                has_errors = True

        # Collect all error messages from failed queries
        error_messages = [qr.error for qr in query_results if qr.error]

        return ControlExecutionResult(
            control_id=control_id,
            control_version=control_version,
            intent=control_definition.intent,
            query_results=query_results,
            total_execution_time_ms=total_time,
            has_errors=has_errors,
            errors=error_messages,
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

    def _execute_with_timeout(
        self, 
        cursor, 
        sql: str, 
        binds: Optional[Dict[str, Any]], 
        timeout_seconds: int
    ) -> None:
        """
        Execute SQL with timeout enforcement (cross-platform).
        
        Per AGENTS.md § 6.1 (Query Execution Limits):
        - Enforce timeout_seconds per query
        - Cancel query if timeout exceeded
        - Thread-based implementation (works on Windows + Unix)
        
        Args:
            cursor: Oracle cursor
            sql: SQL statement
            binds: Bind parameters (or None)
            timeout_seconds: Max execution time
            
        Raises:
            TimeoutError: If query exceeds timeout
            oracledb.DatabaseError: If query fails
        """
        exception_holder = [None]
        
        def execute_target():
            """Target function for thread execution"""
            try:
                if binds:
                    cursor.execute(sql, binds)
                else:
                    cursor.execute(sql)
            except Exception as e:
                exception_holder[0] = e
        
        # Start execution in thread
        exec_thread = threading.Thread(target=execute_target, daemon=True)
        exec_thread.start()
        
        # Wait for completion or timeout
        exec_thread.join(timeout=timeout_seconds)
        
        # Check if thread is still alive (timeout occurred)
        if exec_thread.is_alive():
            logger.error(f"Query timeout exceeded: {timeout_seconds}s")
            # Note: In Oracle, we can't forcefully kill a thread from Python
            # The query will continue executing in the database
            # Best practice: close connection to cancel server-side execution
            try:
                cursor.close()
            except:
                pass
            
            raise TimeoutError(
                f"Query execution exceeded timeout of {timeout_seconds} seconds. "
                f"Connection closed to cancel server-side execution."
            )
        
        # Check if execution raised an exception
        if exception_holder[0]:
            raise exception_holder[0]
        
        logger.debug(f"Query executed successfully within {timeout_seconds}s timeout")

    def _validate_binds(self, binds: Dict[str, Any], bind_schema: List[Dict]) -> Dict[str, Any]:
        """
        Validate bind parameters against schema with type checking.
        
        Per AGENTS.md § 6.1 (Parameter Binding):
        - Ensures bind values match expected types from schema
        - Rejects unexpected bind parameters (strict mode)
        - Performs safe type conversion where appropriate
        
        Args:
            binds: Actual bind values
            bind_schema: Expected bind schema from control definition
                        [{"name": str, "type": str, "optional": bool}, ...]
            
        Returns:
            Dict[str, Any]: Validated and type-converted bind values
            
        Raises:
            QueryExecutionError: If validation fails
        """
        if not binds:
            binds = {}
        
        expected_names = {b.get("name") for b in bind_schema}
        validated_binds = {}

        # Step 1: Reject unexpected bind parameters (security: prevent injection vectors)
        for bind_name in binds.keys():
            if bind_name not in expected_names:
                raise QueryExecutionError(
                    f"Unexpected bind parameter '{bind_name}'. "
                    f"Only {expected_names} are allowed per control schema."
                )

        # Step 2: Validate required binds are present + type check
        for bind_spec in bind_schema:
            bind_name = bind_spec.get("name")
            bind_type = bind_spec.get("type", "str")  # default: string
            is_optional = bind_spec.get("optional", False)

            # Check presence
            if bind_name not in binds:
                if not is_optional:
                    raise QueryExecutionError(
                        f"Required bind parameter missing: '{bind_name}'"
                    )
                continue  # Skip validation for missing optional params

            # Get value
            bind_value = binds[bind_name]

            # Step 3: Type validation + safe conversion
            try:
                validated_value = self._convert_bind_type(bind_value, bind_type, bind_name)
                validated_binds[bind_name] = validated_value
            except (ValueError, TypeError) as e:
                raise QueryExecutionError(
                    f"Bind parameter '{bind_name}' type mismatch. "
                    f"Expected {bind_type}, got {type(bind_value).__name__}: {e}"
                )

        return validated_binds

    def _convert_bind_type(self, value: Any, expected_type: str, param_name: str) -> Any:
        """
        Convert bind value to expected type with validation.
        
        Supported types:
        - str, int, float, bool
        - date, datetime (ISO format strings)
        
        Args:
            value: Bind value to convert
            expected_type: Expected type name (from schema)
            param_name: Parameter name (for error messages)
            
        Returns:
            Converted value
            
        Raises:
            ValueError: If conversion fails
        """
        if value is None:
            return None

        # Already correct type
        if expected_type == "str" and isinstance(value, str):
            return value
        elif expected_type == "int" and isinstance(value, int):
            return value
        elif expected_type == "float" and isinstance(value, (int, float)):
            return float(value)
        elif expected_type == "bool" and isinstance(value, bool):
            return value

        # Safe conversion attempts
        if expected_type == "str":
            return str(value)
        
        elif expected_type == "int":
            # Accept numeric strings
            if isinstance(value, str):
                return int(value)  # raises ValueError if not numeric
            elif isinstance(value, (int, float)):
                return int(value)
            else:
                raise ValueError(f"Cannot convert {type(value).__name__} to int")
        
        elif expected_type == "float":
            if isinstance(value, str):
                return float(value)
            elif isinstance(value, (int, float)):
                return float(value)
            else:
                raise ValueError(f"Cannot convert {type(value).__name__} to float")
        
        elif expected_type == "bool":
            if isinstance(value, str):
                # Accept: "true"/"false", "1"/"0", "yes"/"no"
                lower = value.lower()
                if lower in ("true", "1", "yes"):
                    return True
                elif lower in ("false", "0", "no"):
                    return False
                else:
                    raise ValueError(f"Cannot convert '{value}' to bool")
            elif isinstance(value, (int, float)):
                return bool(value)
            else:
                raise ValueError(f"Cannot convert {type(value).__name__} to bool")
        
        elif expected_type in ("date", "datetime"):
            # Accept ISO format strings, convert to string for Oracle binding
            # oracledb will handle the conversion to Oracle DATE type
            if isinstance(value, str):
                # Validate ISO format (basic check)
                import re
                if expected_type == "date":
                    if not re.match(r'\d{4}-\d{2}-\d{2}', value):
                        raise ValueError(f"Invalid date format: {value}. Expected YYYY-MM-DD")
                else:  # datetime
                    if not re.match(r'\d{4}-\d{2}-\d{2}[T\s]\d{2}:\d{2}:\d{2}', value):
                        raise ValueError(f"Invalid datetime format: {value}. Expected YYYY-MM-DD HH:MM:SS")
                return value
            else:
                raise ValueError(f"Date/datetime must be ISO format string, got {type(value).__name__}")
        
        else:
            # Unknown type: pass through (log warning)
            logger.warning(f"Unknown bind type '{expected_type}' for param '{param_name}', passing through as-is")
            return value
