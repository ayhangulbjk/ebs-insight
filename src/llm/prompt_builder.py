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

    # System prompt (policy + behavior constraints) - OPTIMIZED FOR SPEED
    SYSTEM_PROMPT = """Oracle EBS R12.2 ops assistant. Analyze DB results.

RULES:
- Write 2-5 summary bullets (keep concise and meaningful)
- Include REAL data examples from the samples provided (use actual OBJECT_NAME values)
- Verdict: OK/WARN/CRIT/UNKNOWN
- Evidence: key metrics with actual numbers
- MANDATORY: Write 3-4 detailed Next Steps with specific SQL commands
- Use Turkish if prompt is Turkish
- Use line breaks between sections for readability

OUTPUT STRUCTURE:
**Summary**
- First bullet with count
- Second bullet with REAL examples from data (not generic names)
- Third bullet with context/impact

**Verdict** [verdict here]

**Evidence**
- Metric 1: value
- Metric 2: value

**Next Steps**
- Action 1: specific command or query
- Action 2: what to check and why
- Action 3: troubleshooting step
"""

    @staticmethod
    def build_system_prompt() -> str:
        """Return the system prompt (policy + behavior constraints)."""
        return PromptBuilder.SYSTEM_PROMPT

    @staticmethod
    def build_context_prompt(
        control: ControlDefinition, execution_result: ControlExecutionResult
    ) -> str:
        """
        Build context prompt from control metadata + DB results + knowledge file (if exists).

        Args:
            control: ControlDefinition with metadata
            execution_result: ControlExecutionResult with sanitized DB data

        Returns:
            Context string for Ollama
        """
        lines = []

        # Minimal control metadata (OPTIMIZED)
        lines.append(f"**Control**: {control.title}")
        lines.append(f"**Task**: {control.doc_hint}")
        lines.append("")
        
        # Load domain knowledge if specified
        if control.knowledge_file:
            try:
                import os
                knowledge_path = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
                    "knowledge", "controls", control.knowledge_file
                )
                if os.path.exists(knowledge_path):
                    with open(knowledge_path, 'r', encoding='utf-8') as f:
                        knowledge_content = f.read()
                    lines.append("**Domain Knowledge:**")
                    lines.append(knowledge_content)
                    lines.append("")
                    logger.info(f"Loaded knowledge file: {control.knowledge_file} ({len(knowledge_content)} chars)")
                else:
                    logger.warning(f"Knowledge file not found: {knowledge_path}")
            except Exception as e:
                logger.error(f"Failed to load knowledge file {control.knowledge_file}: {e}")
        
        # Query results (compact format)
        lines.append("**Data:**")
        lines.append("")

        for idx, query_result in enumerate(execution_result.query_results, 1):
            if query_result.error:
                lines.append(f"Error: {query_result.error}")
            elif not query_result.rows:
                lines.append("No data")
            else:
                # OPTIMIZATION: Minimal data format
                row_count = query_result.row_count
                
                if row_count > 10:
                    # Large dataset: aggregated summary only
                    lines.append(f"**Total rows**: {row_count}")
                    
                    # Show first 5 as compact sample (NO TRUNCATION for object names)
                    columns = list(query_result.rows[0].keys())
                    lines.append(f"**Columns**: {', '.join(columns)}")
                    lines.append(f"**Sample (first 5)**:")
                    
                    for i, row in enumerate(query_result.rows[:5], 1):
                        # Show full values (no truncation for clarity)
                        values = [f"{k}={str(v)}" for k, v in row.items()]
                        lines.append(f"  {i}. {'; '.join(values)}")
                    
                    lines.append(f"_(+{row_count - 5} more rows)_")
                else:
                    # Small dataset: show all compactly
                    columns = list(query_result.rows[0].keys())
                    lines.append(f"**Rows**: {row_count}")
                    
                    for i, row in enumerate(query_result.rows, 1):
                        values = [f"{k}={str(v)[:25]}" for k, v in row.items()]
                        lines.append(f"  {i}. {'; '.join(values)}")

            lines.append("")

        # Minimal execution summary
        if execution_result.has_errors:
            lines.append("⚠️ Errors detected")
        # No success message needed - saves tokens

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
