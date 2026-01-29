"""
Result Sanitization & Redaction.
Per AGENTS.md § 6.2 (Result Shaping & Sanitization).

Removes/obfuscates sensitive fields before sending to LLM.
Truncates large text fields.
Caps rows + includes aggregation summary.
"""

import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


class Sanitizer:
    """
    Sanitize query results before passing to LLM.
    
    Per AGENTS.md § 6.2:
    - Remove/obfuscate SENSITIVE fields
    - Truncate large text (> 500 chars)
    - Cap rows (50) + include aggregation
    - Include "data truncated" marker
    """

    # Sensitive field patterns (case-insensitive)
    # Per AGENTS.md § 5.5 (Sensitive Fields)
    SENSITIVE_PATTERNS = {
        "ORACLE_USERNAMES": ["user_name", "username", "owner", "created_by", "modified_by"],
        "EMAIL": ["email", "email_address", "email_addr"],
        "PASSWORDS": ["password", "passwd", "pwd"],
        "TOKENS": ["token", "api_key", "secret", "apikey"],
        "IP_ADDRESSES": ["ip_address", "host", "ip"],
    }

    MAX_TEXT_LENGTH = 500
    MAX_ROWS = 50
    REDACTION_MARKER = "[REDACTED]"
    TRUNCATION_MARKER = "[...truncated]"

    @classmethod
    def sanitize_result(cls, rows: List[Dict[str, Any]], schema: List[Dict]) -> Dict[str, Any]:
        """
        Sanitize query result rows.
        
        Args:
            rows: Query result rows
            schema: Expected result schema (from control definition)
            
        Returns:
            Dict with:
            - rows: Sanitized rows (capped at MAX_ROWS)
            - row_count: Total rows returned
            - truncated: Boolean if truncation occurred
            - truncation_markers_count: Count of [REDACTED]/[...truncated] markers
        """
        sanitized_rows = []
        redaction_count = 0
        truncation_count = 0

        # Identify sensitive columns from schema
        sensitive_columns = cls._identify_sensitive_columns(schema)

        # Process rows
        for row_idx, row in enumerate(rows):
            if row_idx >= cls.MAX_ROWS:
                break

            sanitized_row = {}
            for col_name, col_value in row.items():
                # Check if column is sensitive
                if col_name in sensitive_columns:
                    sanitized_row[col_name] = cls.REDACTION_MARKER
                    redaction_count += 1
                # Truncate large text
                elif isinstance(col_value, str) and len(col_value) > cls.MAX_TEXT_LENGTH:
                    truncated = col_value[: cls.MAX_TEXT_LENGTH] + cls.TRUNCATION_MARKER
                    sanitized_row[col_name] = truncated
                    truncation_count += 1
                else:
                    sanitized_row[col_name] = col_value

            sanitized_rows.append(sanitized_row)

        # Determine if truncation occurred
        rows_truncated = len(rows) > cls.MAX_ROWS

        logger.debug(
            f"Sanitization: {len(sanitized_rows)} rows, "
            f"{redaction_count} redactions, {truncation_count} truncations, "
            f"rows_truncated={rows_truncated}"
        )

        return {
            "rows": sanitized_rows,
            "row_count": len(rows),
            "truncated": rows_truncated,
            "redaction_count": redaction_count,
            "truncation_count": truncation_count,
            "total_markers": redaction_count + truncation_count,
        }

    @classmethod
    def _identify_sensitive_columns(cls, schema: List[Dict]) -> set:
        """
        Identify sensitive columns from result schema.
        
        Per AGENTS.md § 6.2:
        Only columns explicitly marked as sensitive=true in schema are redacted.
        If schema doesn't mark it, it's considered safe to return.
        
        Args:
            schema: Result schema list (from control definition)
                   Expected: [{"name": "col", "sensitive": bool}, ...]
            
        Returns:
            Set of sensitive column names (ONLY those marked sensitive=true)
        """
        sensitive = set()

        for col_spec in schema:
            col_name = col_spec.get("name", "").lower()

            # Only respect explicit sensitive flag from schema
            # Do NOT use pattern matching - schema is SSOT
            if col_spec.get("sensitive", False):
                sensitive.add(col_name)

        logger.debug(f"Identified {len(sensitive)} sensitive columns from schema: {sensitive}")
        return sensitive

    @classmethod
    def format_for_llm(cls, sanitized_result: Dict[str, Any]) -> str:
        """
        Format sanitized result for LLM consumption.
        
        Args:
            sanitized_result: Output from sanitize_result()
            
        Returns:
            Human-readable format for LLM context
        """
        rows = sanitized_result["rows"]
        row_count = sanitized_result["row_count"]
        truncated = sanitized_result["truncated"]
        total_markers = sanitized_result["total_markers"]

        # Header
        lines = [
            f"Query Results: {row_count} rows",
            f"Displayed: {len(rows)} rows (max limit: {cls.MAX_ROWS})",
        ]

        if truncated:
            lines.append(f"⚠️  Rows truncated to {cls.MAX_ROWS} max.")

        if total_markers > 0:
            lines.append(f"⚠️  {total_markers} redactions/truncations applied for data protection.")

        lines.append("")

        # Table format
        if rows:
            # Column headers
            headers = list(rows[0].keys())
            lines.append("| " + " | ".join(headers) + " |")
            lines.append("| " + " | ".join(["---"] * len(headers)) + " |")

            # Data rows
            for row in rows:
                values = [
                    str(row.get(h, "NULL"))[:50]  # Truncate to 50 chars for display
                    for h in headers
                ]
                lines.append("| " + " | ".join(values) + " |")

        lines.append("")

        # Summary
        if row_count == 0:
            lines.append("⚠️  No rows returned.")
        else:
            lines.append(f"Summary: {row_count} rows matched query conditions.")

        return "\n".join(lines)
