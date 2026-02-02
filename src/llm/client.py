"""
Ollama LLM Client.
Per AGENTS.md § 7 (Ollama Prompting Rules).

Connects to Ollama API, handles prompt construction, parses responses.
Implements output validation per SECURITY.MD § 3.3.
"""

import json
import logging
from typing import Optional
import requests
from src.controls.schema import LLMSummaryResponse
from src.llm.input_validator import PromptInjectionDetector

logger = logging.getLogger(__name__)


class OllamaClient:
    """HTTP client for Ollama API."""

    def __init__(self, ollama_url: str, model_name: str, timeout_seconds: int = None):
        """
        Args:
            ollama_url: Base URL (e.g., http://127.0.0.1:11434)
            model_name: Model name (e.g., ebs-qwen25chat:latest)
            timeout_seconds: Request timeout (None = no timeout, wait indefinitely)
        """
        self.ollama_url = ollama_url.rstrip("/")
        self.model_name = model_name
        self.timeout_seconds = timeout_seconds
        self.generate_endpoint = f"{self.ollama_url}/api/generate"

    def verify_connectivity(self) -> bool:
        """Verify Ollama is reachable and model loaded."""
        try:
            response = requests.get(
                f"{self.ollama_url}/api/tags", timeout=5, json=True
            )
            if response.status_code == 200:
                models = response.json().get("models", [])
                model_names = [m.get("name", "") for m in models]
                if self.model_name in model_names:
                    logger.info(f"✓ Ollama connectivity verified, model: {self.model_name}")
                    return True
                else:
                    logger.error(
                        f"✗ Model {self.model_name} not loaded. Available: {model_names}"
                    )
                    return False
        except Exception as e:
            logger.error(f"✗ Ollama connectivity check failed: {e}")
            return False

    def generate_chat_response(self, user_message: str) -> Optional[str]:
        """
        Generate a general chat response (not EBS-specific).
        Used for chit-chat when control match score is too low.
        
        Per AGENTS.md § 2: Chit-chat without DB context.
        
        Args:
            user_message: User's chat message
            
        Returns:
            Response text or None if failed
        """
        system_prompt = (
            "Sen EBS sistemleriyle ilgili soruları yanıtlamaya yardımcı olan bir asistansın. "
            "Eğer EBS sistemiyle ilgili değilse, genel sohbete devam edebilirsin. "
            "Yanıtlarını kısa ve öz tut."
        )
        
        full_prompt = f"{system_prompt}\n\nUser: {user_message}"
        
        try:
            logger.debug(f"Calling Ollama for chat (non-EBS): {self.model_name}")
            
            # OPTIMIZATION: Fast params for chat (shorter, faster responses)
            response = requests.post(
                self.generate_endpoint,
                json={
                    "model": self.model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "temperature": 0.7,  # Higher temperature for conversational responses
                    "top_p": 0.95,
                    "options": {
                        "num_ctx": 1024,      # Smaller context for chat (very fast)
                        "num_predict": 100,   # Short chat responses
                        "num_thread": 8,
                    },
                    "keep_alive": "30m"
                },
                timeout=self.timeout_seconds,
            )
            
            if response.status_code == 200:
                result = response.json()
                chat_response = result.get("response", "").strip()
                
                # SECURITY: Output validation
                if not PromptInjectionDetector.validate_output(chat_response, "chat"):
                    logger.error("Chat response validation failed")
                    return "Üzgünüm, yanıt güvenlik kontrolünden geçemedi."
                
                logger.info(f"✓ Chat response generated ({len(chat_response)} chars)")
                return chat_response
            else:
                logger.error(f"✗ Ollama returned {response.status_code}: {response.text}")
                return None
                
        except requests.Timeout:
            logger.error(f"✗ Ollama chat timeout after {self.timeout_seconds}s")
            return None
        except Exception as e:
            logger.error(f"✗ Ollama chat call failed: {e}")
            return None

    def summarize(
        self, system_prompt: str, context: str, user_question: str
    ) -> Optional[LLMSummaryResponse]:
        """
        Call Ollama to summarize DB results with security markers.

        Args:
            system_prompt: System policy + behavior constraints
            context: Control metadata + DB results (sanitized)
            user_question: Original user prompt (already sanitized)

        Returns:
            LLMSummaryResponse with summary, verdict, evidence, details
        """
        # Import here to avoid circular dependency
        from src.llm.prompt_builder import PromptBuilder
        
        # Build full prompt with security markers
        # Per SECURITY.MD § 3.2 (Context Separation)
        full_prompt = PromptBuilder.build_full_prompt_with_markers(
            system_prompt, context, user_question
        )

        try:
            logger.debug(f"Calling Ollama: {self.model_name} ({self.timeout_seconds}s timeout)")

            # OPTIMIZATION: Aggressive performance tuning
            # num_ctx: Minimal context window
            # num_predict: Short responses only
            # repeat_penalty: Avoid repetition (faster generation)
            # top_k: Limit vocabulary sampling (faster)
            response = requests.post(
                self.generate_endpoint,
                json={
                    "model": self.model_name,
                    "prompt": full_prompt,
                    "stream": False,
                    "temperature": 0.3,  # Low temperature for deterministic summaries
                    "top_p": 0.9,
                    "options": {
                        "num_ctx": 1536,      # Further reduced context (was 2048)
                        "num_predict": 200,   # Max 200 tokens (was 250)
                        "num_thread": 8,      # Use 8 CPU threads
                        "repeat_penalty": 1.2,  # Penalize repetition
                        "top_k": 40,          # Limit token sampling
                        "num_batch": 512,     # Batch size for processing
                    },
                    "keep_alive": "30m"  # Keep in RAM
                },
                timeout=self.timeout_seconds,
            )

            if response.status_code == 200:
                result = response.json()
                raw_response = result.get("response", "").strip()

                # SECURITY: Output validation per SECURITY.MD § 3.3
                if not PromptInjectionDetector.validate_output(raw_response, "summarize"):
                    logger.error("Output validation failed: potential prompt leakage")
                    # Return safe fallback instead of leaked content
                    return LLMSummaryResponse(
                        summary=["System error: Response validation failed"],
                        verdict="UNKNOWN",
                        evidence=[],
                        details="",
                        next_steps=[]
                    )

                # DEBUG: Log raw Ollama response
                logger.debug(f"Raw Ollama response ({len(raw_response)} chars): {raw_response[:500]}...")

                # Parse response into contract
                parsed = self._parse_response(raw_response)
                logger.info(f"✓ Ollama response: {parsed.verdict}")
                return parsed

            else:
                logger.error(
                    f"✗ Ollama returned {response.status_code}: {response.text}"
                )
                return None

        except requests.Timeout:
            logger.error(f"✗ Ollama timeout after {self.timeout_seconds}s")
            return None
        except Exception as e:
            logger.error(f"✗ Ollama call failed: {e}")
            return None

    @staticmethod
    def _parse_response(raw_response: str) -> LLMSummaryResponse:
        """
        Parse raw Ollama response into LLMSummaryResponse contract.

        Expected format:
        ---
        **Summary**
        - bullet 1
        - bullet 2

        **Verdict** OK / WARN / CRIT / UNKNOWN

        **Evidence**
        - key metric 1
        - key metric 2

        **Details** (optional)
        [details text]

        **Next Steps** (optional)
        - suggestion 1
        """
        # Initialize defaults
        summary_bullets = []
        verdict = "UNKNOWN"
        evidence = []
        details = ""
        next_steps = []

        lines = raw_response.split("\n")
        current_section = None

        for line in lines:
            line = line.strip()

            # Section detection
            if line.startswith("**Summary**"):
                current_section = "summary"
                continue
            elif line.startswith("**Verdict**"):
                current_section = "verdict"
                # Extract verdict from this line or next
                parts = line.replace("**Verdict**", "").strip().split()
                if parts:
                    verdict_candidate = parts[0].upper()
                    if verdict_candidate in ["OK", "WARN", "CRIT", "CRITICAL", "UNKNOWN"]:
                        verdict = "CRIT" if verdict_candidate == "CRITICAL" else verdict_candidate
                continue
            elif line.startswith("**Evidence**"):
                current_section = "evidence"
                continue
            elif line.startswith("**Details**"):
                current_section = "details"
                continue
            elif line.startswith("**Next Steps**"):
                current_section = "next_steps"
                continue
            elif line.startswith("**"):
                current_section = None
                continue

            # Content parsing
            if not line:
                continue

            if current_section == "summary" and line.startswith("-"):
                summary_bullets.append(line.lstrip("- ").strip())
            elif current_section == "verdict" and not verdict.startswith("**"):
                verdict_candidate = line.upper()
                if verdict_candidate in ["OK", "WARN", "CRIT", "CRITICAL", "UNKNOWN"]:
                    verdict = "CRIT" if verdict_candidate == "CRITICAL" else verdict_candidate
            elif current_section == "evidence" and line.startswith("-"):
                evidence.append(line.lstrip("- ").strip())
            elif current_section == "details":
                details += line + " "
            elif current_section == "next_steps" and line.startswith("-"):
                next_steps.append(line.lstrip("- ").strip())

        # Ensure minimum requirements
        if not summary_bullets:
            # Try to extract any bullet points from the entire response
            for line in lines:
                line = line.strip()
                if line.startswith("- ") or line.startswith("• "):
                    summary_bullets.append(line.lstrip("- • ").strip())

            if not summary_bullets:
                summary_bullets = ["Analysis completed based on provided data"]

        if not evidence:
            # Try to find any metrics or numbers in the response
            for line in lines:
                line = line.strip()
                if any(keyword in line.lower() for keyword in ["count", "total", "found", "rows", "objects"]):
                    evidence.append(line)
                    break
            if not evidence:
                evidence = ["See query results above"]

        # Try to extract verdict from anywhere in the response
        if verdict == "UNKNOWN":
            for line in lines:
                line = line.upper()
                if "OK" in line and "NOT" not in line:
                    verdict = "OK"
                    break
                elif "WARN" in line or "WARNING" in line:
                    verdict = "WARN"
                    break
                elif "CRIT" in line or "CRITICAL" in line or "ERROR" in line:
                    verdict = "CRIT"
                    break

        logger.debug(f"Parsed response: verdict={verdict}, bullets={len(summary_bullets)}, evidence={len(evidence)}")

        return LLMSummaryResponse(
            summary_bullets=summary_bullets,
            verdict=verdict,
            evidence=evidence,
            details=details.strip() or None,
            next_steps=next_steps or None,
        )
