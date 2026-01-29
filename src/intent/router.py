"""
Score-Based Router - Route EBS-control prompts to correct control(s).
Per AGENTS.md § 5 (Score-Based Routing).

Implements explainable scoring with multiple factors:
- keyword_match_score (0.40 weight)
- intent_match_score (0.35 weight)
- sql_shape_score (0.10 weight, optional)
- recency_boost (0.10 weight)
- priority_boost (0.10 weight)
- ambiguity_penalty (0.05 weight, negative)
"""

import logging
from typing import List, Optional
from datetime import datetime
import uuid

from src.controls.schema import (
    ControlDefinition,
    RouterDecision,
    CandidateScore,
    LLMOutputVerdictType,
)

logger = logging.getLogger(__name__)


class RouterScore:
    """Scoring components for a control candidate"""

    def __init__(self):
        self.keyword_match = 0.0
        self.intent_match = 0.0
        self.sql_shape = 0.0
        self.recency = 0.0
        self.priority = 0.0
        self.ambiguity_penalty = 0.0
        self.final = 0.0


class ScoreBasedRouter:
    """
    Route EBS-control prompts to correct control(s) with explainable scoring.
    
    Per AGENTS.md § 5.1 (Router Output Must Be Explainable):
    Produces decision object with:
    - Top-N candidates with score breakdown
    - Selected control + justification
    - Ambiguity detection and clarification questions
    """

    CONFIDENCE_THRESHOLD = 0.45  # Min score for auto-selection (keyword matching can be challenging)
    AMBIGUITY_THRESHOLD = 0.05  # Gap between 1st/2nd for tie detection
    TOP_N_CANDIDATES = 5

    # Special control categories
    CRITICAL_CONTROLS = []  # Can be populated from catalog
    HEALTH_BUNDLE = [
        "concurrent_mgr_health",
        "invalid_objects",
        "active_users",
    ]

    def __init__(self, catalog):
        """
        Initialize router with control catalog.
        
        Args:
            catalog: ControlCatalog instance
        """
        self.catalog = catalog

    def route(self, user_prompt: str, intent: str) -> RouterDecision:
        """
        Route prompt to control(s) with explainable scoring.
        
        Per AGENTS.md § 5.1 (Router Output Must Be Explainable)
        Per AGENTS.md § 5.3 (Ambiguity Handling)
        
        Args:
            user_prompt: User's question
            intent: Detected intent (chit_chat, ebs_control, ambiguous, unknown)
            
        Returns:
            RouterDecision with candidates, selected control, and justification
        """
        request_id = f"req_{str(uuid.uuid4())[:8]}"
        
        logger.info(f"[{request_id}] Routing prompt: intent={intent}")

        # Step 1: Get all controls (if no specific intent, use all)
        # =========================================================
        matching_controls = self.catalog.get_all_controls()

        if not matching_controls:
            logger.warning(f"[{request_id}] No controls in catalog")
            return RouterDecision(
                request_id=request_id,
                prompt_intent="unknown",
                intent_confidence=0.0,
                candidates=[],
                selected_control_id=None,
                confidence=0.0,
                justification="Catalog is empty or no matching controls found",
                ambiguity_threshold_breach=True,
                suggested_interpretations=[],
            )

        # Step 2: Calculate score for each control
        # ========================================
        candidates = []
        for control in matching_controls:
            score = self._calculate_score(user_prompt, control)
            candidates.append(
                CandidateScore(
                    control_id=control.control_id,
                    control_version=control.version,
                    keyword_match_score=score.keyword_match,
                    intent_match_score=score.intent_match,
                    sql_shape_score=score.sql_shape,
                    recency_boost=score.recency,
                    priority_boost=score.priority,
                    ambiguity_penalty=score.ambiguity_penalty,
                    final_score=score.final,
                )
            )

        # Step 3: Sort by final_score (descending)
        # ========================================
        candidates = sorted(candidates, key=lambda c: c.final_score, reverse=True)
        top_candidate = candidates[0]

        logger.debug(
            f"[{request_id}] Top candidate: {top_candidate.control_id} "
            f"(score={top_candidate.final_score:.3f})"
        )

        # Step 4: Check confidence threshold
        # ==================================
        if top_candidate.final_score < self.CONFIDENCE_THRESHOLD:
            logger.info(
                f"[{request_id}] Confidence below threshold: "
                f"{top_candidate.final_score:.2%}"
            )
            return RouterDecision(
                request_id=request_id,
                prompt_intent=intent,
                intent_confidence=top_candidate.final_score,
                candidates=candidates[: self.TOP_N_CANDIDATES],
                selected_control_id=None,
                confidence=0.0,
                justification=(
                    f"Confidence below threshold ({top_candidate.final_score:.1%}). "
                    f"Lütfen sorunuzu daha açık yazabilir misiniz?"
                ),
                ambiguity_threshold_breach=True,
                suggested_interpretations=self._get_suggestions(candidates[:3]),
            )

        # Step 5: Check for tie (close scores)
        # ====================================
        if len(candidates) > 1:
            score_gap = (
                candidates[0].final_score - candidates[1].final_score
            )
            if score_gap < self.AMBIGUITY_THRESHOLD:
                logger.info(
                    f"[{request_id}] Ambiguous: top 2 candidates "
                    f"within {self.AMBIGUITY_THRESHOLD:.2%} gap"
                )
                return RouterDecision(
                    request_id=request_id,
                    prompt_intent=intent,
                    intent_confidence=top_candidate.final_score,
                    candidates=candidates[: self.TOP_N_CANDIDATES],
                    selected_control_id=top_candidate.control_id,
                    selected_control_version=top_candidate.control_version,
                    confidence=top_candidate.final_score,
                    justification=(
                        f"Seçilen kontrol: {self.catalog.get_control(top_candidate.control_id).title}. "
                        f"Ancak başka yorumlamalar da olası olduğu için lütfen doğrulama yapın."
                    ),
                    ambiguity_threshold_breach=True,
                    suggested_interpretations=self._get_suggestions(candidates[:3]),
                )

        # Step 6: Select control (no ambiguity, confidence high)
        # =====================================================
        justification = self._build_justification(top_candidate, user_prompt)

        logger.info(
            f"[{request_id}] Selected: {top_candidate.control_id} "
            f"(confidence={top_candidate.final_score:.2%})"
        )

        return RouterDecision(
            request_id=request_id,
            prompt_intent=intent,
            intent_confidence=top_candidate.final_score,
            candidates=candidates[: self.TOP_N_CANDIDATES],
            selected_control_id=top_candidate.control_id,
            selected_control_version=top_candidate.control_version,
            confidence=top_candidate.final_score,
            justification=justification,
            ambiguity_threshold_breach=False,
            suggested_interpretations=[],
        )

    def _calculate_score(self, user_prompt: str, control: ControlDefinition) -> RouterScore:
        """
        Calculate comprehensive score for a control.
        
        Per AGENTS.md § 5.2 (Score Formula):
        final_score = (
            keyword_match * 0.40 +
            intent_match * 0.35 +
            sql_shape * 0.10 +
            recency * 0.10 -
            ambiguity_penalty * 0.05
        )
        """
        score = RouterScore()

        # 1. KEYWORD MATCH SCORE
        # ======================
        score.keyword_match = self._calculate_keyword_match(user_prompt, control)

        # 2. INTENT MATCH SCORE
        # =====================
        score.intent_match = 1.0  # For now, all controls are considered

        # 3. SQL SHAPE SCORE (optional)
        # =============================
        score.sql_shape = self._calculate_sql_shape_score(control)

        # 4. RECENCY BOOST
        # ================
        score.recency = self._calculate_recency_boost(control.version)

        # 5. PRIORITY BOOST
        # =================
        score.priority = 0.05 if control.control_id in self.HEALTH_BUNDLE else 0.0

        # 6. AMBIGUITY PENALTY
        # ====================
        ambiguous_keywords = ["status", "check", "health", "durumu", "kontrol", "nedir"]
        prompt_lower = user_prompt.lower()
        vague_count = sum(
            1 for kw in ambiguous_keywords if kw in prompt_lower
        )
        score.ambiguity_penalty = 0.05 if vague_count > 2 else 0.0

        # FINAL SCORE
        # ===========
        score.final = (
            score.keyword_match * 0.40
            + score.intent_match * 0.35
            + score.sql_shape * 0.10
            + score.recency * 0.10
            - score.ambiguity_penalty * 0.05
        )

        return score

    def _calculate_keyword_match(self, user_prompt: str, control: ControlDefinition) -> float:
        """
        Calculate keyword match score (0.0-1.0).
        
        Exact match > substring match > fuzzy match
        """
        prompt_lower = user_prompt.lower()
        prompt_words = set(prompt_lower.split())
        
        matched_count = 0
        
        # Check all keywords
        all_keywords = control.keywords.en + control.keywords.tr
        for keyword in all_keywords:
            keyword_lower = keyword.lower()
            keyword_words = set(keyword_lower.split())

            # Exact phrase match
            if keyword_lower in prompt_lower:
                matched_count += 1.0
            # Word-level match (any keyword word in prompt)
            elif any(word in prompt_words for word in keyword_words):
                matched_count += 0.8
            # Fuzzy match on words
            elif self._fuzzy_match(keyword_lower, prompt_lower):
                matched_count += 0.5

        # Average by number of keywords
        if len(all_keywords) > 0:
            return min(1.0, matched_count / len(all_keywords))
        return 0.0

    def _fuzzy_match(self, keyword: str, prompt: str, threshold: float = 0.8) -> bool:
        """Simple fuzzy matching (Levenshtein-like)"""
        from difflib import SequenceMatcher

        words = prompt.split()
        for word in words:
            similarity = SequenceMatcher(None, keyword, word).ratio()
            if similarity >= threshold:
                return True
        return False

    def _calculate_sql_shape_score(self, control: ControlDefinition) -> float:
        """Calculate SQL shape score based on query complexity"""
        query_count = len(control.queries)
        result_columns = sum(len(q.result_schema) for q in control.queries)

        if query_count >= 3 and result_columns >= 10:
            return 0.8
        elif query_count == 1 and result_columns < 5:
            return 0.3
        else:
            return 0.5

    def _calculate_recency_boost(self, version: str) -> float:
        """Boost score for recent control versions"""
        # Simple: assume version format is date (YYYY-MM-DD) or semver
        try:
            # Try parsing as date
            version_date = datetime.strptime(version.split(".")[0], "%Y-%m-%d")
            days_old = (datetime.now() - version_date).days

            if days_old < 30:
                return 0.10
            elif days_old < 90:
                return 0.07
            elif days_old < 180:
                return 0.03
            else:
                return 0.0
        except ValueError:
            # Not a date, default boost
            return 0.05

    def _build_justification(self, candidate: CandidateScore, user_prompt: str) -> str:
        """Build human-readable justification for selection"""
        control = self.catalog.get_control(candidate.control_id)

        parts = []
        if candidate.keyword_match_score > 0.8:
            parts.append(f"Yüksek anahtar kelime eşleşmesi ({candidate.keyword_match_score:.0%})")
        elif candidate.keyword_match_score > 0.5:
            parts.append(f"Orta düzey anahtar kelime eşleşmesi ({candidate.keyword_match_score:.0%})")

        parts.append(f"Kontrol: {control.title}")

        return ". ".join(parts)

    def _get_suggestions(self, top_candidates: List[CandidateScore]) -> List[str]:
        """Get example prompts for ambiguous interpretations"""
        suggestions = []
        for candidate in top_candidates[:3]:
            control = self.catalog.get_control(candidate.control_id)
            # Use first few keywords as examples
            en_examples = control.keywords.en[:2]
            tr_examples = control.keywords.tr[:2]
            suggestion = f"{control.title}: {', '.join(en_examples)} / {', '.join(tr_examples)}"
            suggestions.append(suggestion)
        return suggestions
