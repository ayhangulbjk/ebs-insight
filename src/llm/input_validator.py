"""
Input Validation & Prompt Injection Defense.
Per SECURITY.md § 3 (Prompt Injection Defense).

Validates user input for:
- Length limits
- Control character sanitization
- Injection pattern detection
- Malicious prompt patterns
"""

import re
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class InputValidationError(Exception):
    """Raised when input validation fails"""
    pass


class PromptInjectionDetector:
    """
    Detect and prevent prompt injection attacks.
    
    Per SECURITY.MD § 3.1 (Input Validation):
    - Max length: 2000 characters
    - Strip control characters
    - Detect injection patterns
    """
    
    MAX_LENGTH = 2000
    
    # Prompt injection patterns (case-insensitive)
    INJECTION_PATTERNS = [
        # System prompt manipulation
        r"ignore\s+(previous|all|above|prior).*?(instructions?|prompts?|rules?)",
        r"disregard\s+(previous|all|above|prior).*?(instructions?|prompts?|rules?)",
        r"forget\s+(everything|all|previous)",
        
        # System prompt leakage attempts
        r"(show|print|display|reveal|output).*?(your|the)\s+system\s+prompt",
        r"what.*?(is|are)\s+your\s+(instructions?|prompts?|rules?)",
        r"repeat\s+your\s+(instructions?|prompts?)",
        
        # Role manipulation
        r"you\s+are\s+now\s+(a|an)\s+",
        r"act\s+as\s+(a|an)\s+",
        r"pretend\s+(you|to)\s+(are|be)",
        r"new\s+(role|instructions?|mode)",
        
        # Jailbreak attempts
        r"dan\s+mode",
        r"developer\s+mode",
        r"god\s+mode",
        r"sudo\s+mode",
        
        # Direct prompt injection markers
        r"<\|im_start\|>",
        r"<\|im_end\|>",
        r"\[INST\]",
        r"\[/INST\]",
        r"###\s+System:",
        r"###\s+User:",
        
        # SQL injection attempts (belt-and-suspenders)
        r";\s*(drop|delete|truncate|alter)\s+",
        r"union\s+select",
        r"exec\s*\(",
    ]
    
    # Control characters to strip (except common whitespace)
    CONTROL_CHARS = r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'
    
    @classmethod
    def validate_and_sanitize(cls, user_input: str, request_id: str = "unknown") -> Tuple[str, bool, Optional[str]]:
        """
        Validate and sanitize user input.
        
        Args:
            user_input: Raw user input
            request_id: Request ID for logging
            
        Returns:
            Tuple of (sanitized_input, is_suspicious, warning_message)
            - sanitized_input: Cleaned input (safe to use)
            - is_suspicious: True if injection patterns detected
            - warning_message: Description of issue (if suspicious)
            
        Raises:
            InputValidationError: If input is fundamentally invalid
        """
        if not user_input:
            raise InputValidationError("Empty input")
        
        # Step 1: Length check
        if len(user_input) > cls.MAX_LENGTH:
            logger.warning(
                f"[{request_id}] Input exceeds max length: "
                f"{len(user_input)} > {cls.MAX_LENGTH}"
            )
            raise InputValidationError(
                f"Input too long: {len(user_input)} characters "
                f"(max: {cls.MAX_LENGTH})"
            )
        
        # Step 2: Strip control characters
        sanitized = re.sub(cls.CONTROL_CHARS, '', user_input)
        
        # Step 3: Normalize whitespace (collapse multiple spaces/newlines)
        sanitized = re.sub(r'\s+', ' ', sanitized).strip()
        
        if not sanitized:
            raise InputValidationError("Input contains only control characters")
        
        # Step 4: Check for injection patterns
        is_suspicious = False
        matched_pattern = None
        
        for pattern in cls.INJECTION_PATTERNS:
            if re.search(pattern, sanitized, re.IGNORECASE):
                is_suspicious = True
                matched_pattern = pattern
                logger.warning(
                    f"[{request_id}] INJECTION ATTEMPT DETECTED: "
                    f"pattern='{pattern}', input='{sanitized[:100]}'"
                )
                break
        
        # Step 5: Generate warning message
        warning_message = None
        if is_suspicious:
            warning_message = (
                "Your input contains patterns that may be attempting prompt injection. "
                "This has been flagged for security review."
            )
        
        return sanitized, is_suspicious, warning_message
    
    @classmethod
    def add_context_markers(cls, db_results: str, user_prompt: str) -> str:
        """
        Add context separation markers to prevent prompt injection.
        
        Per SECURITY.MD § 3.2 (Context Separation):
        Clearly mark boundaries between DB results and user input.
        
        Args:
            db_results: Sanitized DB results (from prompt_builder)
            user_prompt: User's question (already sanitized)
            
        Returns:
            Marked context string
        """
        marked = []
        
        # DB Results section
        marked.append("--- START DB RESULTS ---")
        marked.append(db_results)
        marked.append("--- END DB RESULTS ---")
        marked.append("")
        
        # User Question section
        marked.append("--- USER QUESTION ---")
        marked.append(user_prompt)
        marked.append("--- END USER QUESTION ---")
        
        return "\n".join(marked)
    
    @classmethod
    def validate_output(cls, llm_response: str, request_id: str = "unknown") -> bool:
        """
        Validate LLM output for suspicious content.
        
        Per SECURITY.MD § 3.3 (Output Validation):
        Check if LLM response contains leaked system prompts or injection attempts.
        
        Args:
            llm_response: Raw LLM response
            request_id: Request ID for logging
            
        Returns:
            True if response is safe, False if suspicious
        """
        # Check for system prompt leakage
        leakage_patterns = [
            r"You are an Oracle EBS",  # Our system prompt
            r"SYSTEM_PROMPT",
            r"<\|system\|>",
            r"###\s+System:",
        ]
        
        for pattern in leakage_patterns:
            if re.search(pattern, llm_response, re.IGNORECASE):
                logger.error(
                    f"[{request_id}] SYSTEM PROMPT LEAKAGE DETECTED: "
                    f"pattern='{pattern}' in response"
                )
                return False
        
        # Check for abnormally long responses (potential context stuffing)
        MAX_RESPONSE_LENGTH = 10000  # 10KB
        if len(llm_response) > MAX_RESPONSE_LENGTH:
            logger.warning(
                f"[{request_id}] Response too long: {len(llm_response)} chars"
            )
            # Don't reject, just warn (LLM might be verbose)
        
        return True
