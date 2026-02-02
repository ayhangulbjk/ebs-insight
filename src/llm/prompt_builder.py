"""
Prompt Builder for Ollama.
Per AGENTS.md § 7 (Ollama Prompting Rules).

Constructs system + context + user prompts from control metadata + DB results.
Implements context separation markers per SECURITY.MD § 3.2.
"""

import logging
from typing import List, Dict, Any
from src.controls.schema import ControlDefinition, ControlExecutionResult

logger = logging.getLogger(__name__)


class PromptBuilder:
    """Build system and context prompts for Ollama."""

    # System prompt (policy + behavior constraints)
    SYSTEM_PROMPT = """You are an Oracle EBS R12.2 operations assistant.

Your role:
- Analyze provided database results
- Summarize findings in 2-5 bullet points
- Assign a health verdict: OK (normal), WARN (attention needed), CRIT (critical issue), UNKNOWN (insufficient data)
- Provide evidence (key metrics, row counts)
- Suggest next checks if confidence is low

Critical Rules:
- ONLY summarize from provided data. DO NOT invent data.
- If data is missing or inconclusive, say so and suggest next diagnostic steps.
- Keep summary concise and actionable.
- Use Turkish labels if original prompt was Turkish, otherwise English.
- For SENSITIVE data marked [REDACTED]: acknowledge data was protected but do not speculate.

Output Format:
---
**Summary**
- bullet 1
- bullet 2
- [up to 5 bullets]

**Verdict** [OK | WARN | CRIT | UNKNOWN]

**Evidence**
- key metric with value
- [2-3 evidence points]

**Details** (optional, keep compact)
[relevant details if space permits]

**Next Steps** (optional, suggest if needed)
- next diagnostic check if low confidence
---"""

    @staticmethod
    def build_system_prompt() -> str:
        """Return the system prompt (policy + behavior constraints)."""
        return PromptBuilder.SYSTEM_PROMPT

    @staticmethod
    def build_context_prompt(
        control: ControlDefinition, execution_result: ControlExecutionResult
    ) -> str:
        """
        Build context prompt from control metadata + DB results.

        Args:
            control: ControlDefinition with metadata
            execution_result: ControlExecutionResult with sanitized DB data

        Returns:
            Context string for Ollama
        """
        lines = []

        # Control metadata
        lines.append(f"**Control**: {control.title} (v{control.version})")
        lines.append(f"**Intent**: {control.intent}")
        lines.append(f"**Description**: {control.description}")
        lines.append("")

        # What to look for
        lines.append("**What to Look For**")
        lines.append(control.doc_hint)
        lines.append("")

        # Analysis guidance
        if control.analysis_prompt:
            lines.append("**Analysis Focus**")
            lines.append(control.analysis_prompt)
            lines.append("")

        # Query results
        lines.append("**Database Results**")
        lines.append("")

        for idx, query_result in enumerate(execution_result.query_results, 1):
            query_def = next(
                (q for q in control.queries if q.query_id == query_result.query_id),
                None,
            )
            query_name = query_def.query_id if query_def else f"Query_{idx}"

            lines.append(f"_Query {idx}: {query_name}_")

            if query_result.error:
                lines.append(f"**Error**: {query_result.error}")
            elif not query_result.rows:
                lines.append("(No rows)")
            else:
                # OPTIMIZATION: Send aggregated summary instead of full rows to prevent Ollama timeout
                row_count = query_result.row_count
                
                if row_count > 20:
                    # For large result sets, send aggregated data only
                    lines.append(f"**Total Rows**: {row_count}")
                    lines.append("")
                    
                    # Show top 5 rows as sample
                    columns = list(query_result.rows[0].keys())
                    lines.append("**Sample (First 5):**")
                    lines.append("")
                    lines.append("| " + " | ".join(columns) + " |")
                    lines.append("|" + "|".join(["---"] * len(columns)) + "|")
                    
                    for row in query_result.rows[:5]:
                        values = [str(row.get(col, ""))[:30] for col in columns]  # Truncate long values
                        lines.append("| " + " | ".join(values) + " |")
                    
                    lines.append(f"\n_Showing 5 of {row_count} total rows. Full list truncated for performance._")
                else:
                    # For smaller result sets, show all rows
                    columns = list(query_result.rows[0].keys())
                    lines.append("")
                    lines.append("| " + " | ".join(columns) + " |")
                    lines.append("|" + "|".join(["---"] * len(columns)) + "|")

                    display_limit = min(10, len(query_result.rows))
                    for row in query_result.rows[:display_limit]:
                        values = [str(row.get(col, "")) for col in columns]
                        lines.append("| " + " | ".join(values) + " |")

                    if query_result.truncated:
                        lines.append(f"\n_... ({query_result.row_count} total rows, showing {display_limit})_")
                    elif query_result.row_count > display_limit:
                        lines.append(f"\n_({query_result.row_count} total rows, showing {display_limit})_")
                    else:
                        lines.append(f"\n_({query_result.row_count} total rows)_")

            lines.append("")

        # Execution summary
        if execution_result.has_errors:
            lines.append("⚠️  **Execution Note**: Some queries encountered errors. See details above.")
        else:
            lines.append(f"✓ **Execution**: All {len(execution_result.query_results)} queries completed successfully.")

        lines.append(f"**Total Time**: {execution_result.total_execution_time_ms}ms")

        return "\n".join(lines)

    @staticmethod
    def build_user_prompt(original_prompt: str) -> str:
        """
        Build user question for context with separation markers.
        
        Per SECURITY.MD § 3.2 (Context Separation):
        Clearly mark boundaries to prevent prompt injection.

        Args:
            original_prompt: Original user question (already sanitized)

        Returns:
            Formatted user question with markers
        """
        return f"Based on the above database results, answer the user's question:\n\n--- USER QUESTION ---\n{original_prompt}\n--- END USER QUESTION ---"

    @staticmethod
    def build_full_prompt_with_markers(
        system_prompt: str, 
        context: str, 
        user_question: str
    ) -> str:
        """
        Build full prompt with security markers.
        
        Per SECURITY.MD § 3.2 (Context Separation):
        Separate DB results and user input with explicit markers.
        
        Args:
            system_prompt: System policy
            context: Control metadata + DB results
            user_question: User's original question (sanitized)
            
        Returns:
            Full prompt with separation markers
        """
        parts = []
        
        parts.append(system_prompt)
        parts.append("")
        parts.append("--- START DB RESULTS ---")
        parts.append(context)
        parts.append("--- END DB RESULTS ---")
        parts.append("")
        parts.append("--- USER QUESTION ---")
        parts.append(user_question)
        parts.append("--- END USER QUESTION ---")
        
        return "\n".join(parts)
