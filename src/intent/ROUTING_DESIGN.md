"""
ROUTING LOGIC PSEUDO-CODE DESIGN
Per AGENTS.md § 5 (Score-Based Routing)

This file contains the architectural design and pseudo-code for the
intent classification and score-based control routing system.

==============================================================================
HIGH-LEVEL FLOW:
==============================================================================

    USER PROMPT
         |
         v
    [INTENT CLASSIFIER] (ML-based)
         |
         +-- Chit-chat (confidence > 80%) --> Return to Ollama (no DB)
         |
         +-- EBS-Control (confidence > 60%) --> Route to Controls
         |
         +-- Ambiguous (60% > confidence > 30%) --> Ask clarification
         |
         +-- Unknown (confidence < 30%) --> Generic response

    If EBS-Control:
         |
         v
    [SCORE-BASED ROUTER]
         |
         +-- Search keywords in control catalog
         +-- Calculate scores for each candidate
         +-- Rank by final_score
         +-- Check confidence threshold
         +-- Select top control (or top 3 if ambiguous)
         |
         v
    [RETURN ROUTER DECISION]
         {
           request_id: "xxx",
           intent: "ebs_control",
           intent_confidence: 0.92,
           candidates: [{control_id, scores...}, ...],
           selected_control_id: "concurrent_mgr_health",
           justification: "High keyword match for 'concurrent manager'",
           ambiguity_threshold_breach: false
         }

==============================================================================
INTENT CLASSIFIER PSEUDO-CODE:
==============================================================================

class IntentClassifier:
    """
    ML-based intent classification (Naive Bayes or TF-IDF).
    
    Per AGENTS.md § 5 (Score-Based Routing):
    Classify prompt as: chit_chat, ebs_control, ambiguous, unknown
    
    Training Data Strategy:
    - Positive EBS samples: prompts containing EBS keywords
    - Negative (chit-chat) samples: generic conversational text
    - Turkish + English examples for multilingual support
    """
    
    CHIT_CHAT_THRESHOLD = 0.80    # Confidence > 80% => definitely chit-chat
    EBS_CONTROL_THRESHOLD = 0.60  # Confidence > 60% => likely EBS control
    AMBIGUOUS_THRESHOLD = 0.30    # 30% < confidence < 60% => ambiguous
    
    def __init__(self, catalog: ControlCatalog):
        """
        Initialize classifier with training data from catalog keywords.
        
        Algorithm:
        1. Extract all EBS keywords from catalog (English + Turkish)
        2. Collect negative samples (chit-chat phrases)
        3. Train Naive Bayes or TF-IDF vectorizer
        4. Store model for inference
        """
        pass
    
    def classify(self, user_prompt: str) -> IntentClassificationResult:
        """
        Classify user prompt intent.
        
        PSEUDO-CODE:
        ```
        function classify(user_prompt):
            # Preprocess: lowercase, remove punctuation
            preprocessed = preprocess(user_prompt)
            
            # Vectorize: TF-IDF or Naive Bayes features
            features = vectorizer.transform([preprocessed])
            
            # Predict: using trained ML model
            predictions = model.predict_proba(features)[0]
            
            # Get scores for each class
            chit_chat_score = predictions[CHIT_CHAT_CLASS]
            ebs_control_score = predictions[EBS_CONTROL_CLASS]
            
            # Determine intent with confidence thresholds
            if chit_chat_score > CHIT_CHAT_THRESHOLD:
                intent = "chit_chat"
                confidence = chit_chat_score
            elif ebs_control_score > EBS_CONTROL_THRESHOLD:
                intent = "ebs_control"
                confidence = ebs_control_score
            elif max(chit_chat_score, ebs_control_score) > AMBIGUOUS_THRESHOLD:
                intent = "ambiguous"
                confidence = max(chit_chat_score, ebs_control_score)
            else:
                intent = "unknown"
                confidence = max(chit_chat_score, ebs_control_score)
            
            return IntentClassificationResult(
                intent=intent,
                confidence=confidence,
                chit_chat_score=chit_chat_score,
                ebs_control_score=ebs_control_score
            )
        ```
        
        Returns:
            IntentClassificationResult with:
            - intent: one of [chit_chat, ebs_control, ambiguous, unknown]
            - confidence: float (0.0-1.0)
            - all_scores: {class: score, ...}
        """
        pass


==============================================================================
SCORE-BASED ROUTER PSEUDO-CODE:
==============================================================================

class ScoreBasedRouter:
    """
    Route EBS-control prompts to correct control(s) using explainable scoring.
    
    Per AGENTS.md § 5.1 (Router Output Must Be Explainable):
    Each candidate must have score breakdown:
    - keyword_match_score: how many keywords in prompt match control
    - intent_match_score: does control's intent match classified intent
    - sql_shape_score: (optional) based on query complexity
    - recency_boost: prefer recent versions
    - priority_boost: special categories (health bundle, critical)
    - ambiguity_penalty: reduce score if ambiguous match
    
    Final Score Formula (AGENTS.md § 5.2):
    final_score = (
        keyword_match_score * 0.40 +
        intent_match_score * 0.35 +
        sql_shape_score * 0.10 +
        recency_boost * 0.10 -
        ambiguity_penalty * 0.05
    )
    """
    
    CONFIDENCE_THRESHOLD = 0.70   # Selected control score must be > 70%
    AMBIGUITY_THRESHOLD = 0.05    # Gap between 1st and 2nd < 5% = ambiguous
    
    def __init__(self, catalog: ControlCatalog):
        """Initialize router with loaded catalog"""
        self.catalog = catalog
    
    def route(self, user_prompt: str, intent: str) -> RouterDecision:
        """
        Route prompt to control(s) with explainable scoring.
        
        PSEUDO-CODE:
        ```
        function route(user_prompt, intent):
            request_id = generate_request_id()
            candidates = []
            
            # Step 1: Get all controls matching the detected intent
            # ===================================================
            matching_controls = catalog.get_controls_by_intent(intent)
            
            if not matching_controls:
                return RouterDecision(
                    request_id=request_id,
                    prompt_intent="unknown",
                    intent_confidence=0.0,
                    candidates=[],
                    selected_control_id=None,
                    justification="No controls found for this intent",
                    ambiguity_threshold_breach=true
                )
            
            # Step 2: Calculate score for each candidate
            # ============================================
            for control in matching_controls:
                score = calculate_score(user_prompt, control, intent)
                candidates.append(CandidateScore(
                    control_id=control.control_id,
                    control_version=control.version,
                    keyword_match_score=score.keyword_match,
                    intent_match_score=score.intent_match,
                    sql_shape_score=score.sql_shape,
                    recency_boost=score.recency,
                    priority_boost=score.priority,
                    ambiguity_penalty=score.ambiguity_penalty,
                    final_score=score.final
                ))
            
            # Step 3: Sort by final_score (descending)
            # =========================================
            candidates = sorted(candidates, key=lambda c: c.final_score, desc=true)
            top_candidate = candidates[0]
            
            # Step 4: Check confidence threshold
            # ===================================
            if top_candidate.final_score < CONFIDENCE_THRESHOLD:
                return RouterDecision(
                    request_id=request_id,
                    prompt_intent=intent,
                    intent_confidence=top_candidate.final_score,
                    candidates=candidates[:3],
                    selected_control_id=None,
                    justification="Confidence below threshold ({:.2f}%)".format(
                        top_candidate.final_score * 100
                    ),
                    ambiguity_threshold_breach=true,
                    suggested_interpretations=get_suggestions(candidates[:3])
                )
            
            # Step 5: Check for tie (close scores)
            # ====================================
            if len(candidates) > 1:
                score_gap = candidates[0].final_score - candidates[1].final_score
                if score_gap < AMBIGUITY_THRESHOLD:
                    # Tie: present top 3 interpretations
                    return RouterDecision(
                        request_id=request_id,
                        prompt_intent=intent,
                        intent_confidence=top_candidate.final_score,
                        candidates=candidates[:3],
                        selected_control_id=top_candidate.control_id,
                        justification="Multiple interpretations close in score. "
                                      "Selected best match but ambiguity detected.",
                        ambiguity_threshold_breach=true,
                        suggested_interpretations=get_suggestions(candidates[:3])
                    )
            
            # Step 6: Deterministic tie-breaking (if needed)
            # =============================================
            # Per AGENTS.md § 5.2 (Deterministic Tie-Breaking):
            # If scores still tied:
            # 1. prefer controls with higher intent match
            # 2. then higher keyword confidence
            # 3. then fewer queries (simpler)
            # 4. then stable priority order defined in catalog
            
            if multiple_tied_candidates:
                top_candidate = apply_tie_breaker(tied_candidates)
            
            # Step 7: Return decision
            # ======================
            return RouterDecision(
                request_id=request_id,
                prompt_intent=intent,
                intent_confidence=top_candidate.final_score,
                candidates=candidates,
                selected_control_id=top_candidate.control_id,
                selected_control_version=top_candidate.control_version,
                justification=build_justification(top_candidate, user_prompt),
                ambiguity_threshold_breach=false
            )
        ```
        
        Returns:
            RouterDecision (AGENTS.md § 5.1): explainable decision with scores
        """
        pass


==============================================================================
SCORE CALCULATION PSEUDO-CODE:
==============================================================================

function calculate_score(user_prompt, control, intent):
    """
    Calculate comprehensive score for a control candidate.
    
    PSEUDO-CODE:
    ```
    score = Score()
    
    # 1. KEYWORD MATCH SCORE (0.0-1.0)
    # ===================================
    # Count how many control keywords appear in user_prompt
    # Boost: exact phrase match > substring match > partial match
    # Support both EN and TR keywords
    
    matched_en_keywords = []
    matched_tr_keywords = []
    prompt_lower = user_prompt.lower()
    
    for keyword in control.keywords.en:
        if is_exact_phrase_match(keyword, prompt_lower):
            matched_en_keywords.append((keyword, 1.0))  # 100% confidence
        elif is_substring_match(keyword, prompt_lower):
            matched_en_keywords.append((keyword, 0.7))  # 70% confidence
        elif is_fuzzy_match(keyword, prompt_lower):     # handle typos
            matched_en_keywords.append((keyword, 0.4))  # 40% confidence
    
    for keyword in control.keywords.tr:
        # Same logic for Turkish
        ...
    
    total_matched = len(matched_en_keywords) + len(matched_tr_keywords)
    total_keywords = len(control.keywords.en) + len(control.keywords.tr)
    
    # Weighted average of matched keywords
    if total_keywords > 0:
        match_sum = sum(score for _, score in matched_en_keywords + matched_tr_keywords)
        keyword_match_score = match_sum / total_keywords
    else:
        keyword_match_score = 0.0
    
    score.keyword_match = keyword_match_score
    
    # 2. INTENT MATCH SCORE (0.0-1.0)
    # ================================
    # Does control's intent match the detected intent?
    
    if control.intent == detected_intent:
        score.intent_match = 1.0
    else:
        score.intent_match = 0.0
    
    # 3. SQL SHAPE SCORE (0.0-1.0, optional)
    # =======================================
    # Based on query complexity (optional scoring)
    # More complex queries might be better for detailed questions
    
    query_count = len(control.queries)
    result_columns = sum(len(q.result_schema) for q in control.queries)
    
    if query_count >= 3 and result_columns >= 10:
        score.sql_shape = 0.8  # Complex = detailed insights
    elif query_count == 1 and result_columns < 5:
        score.sql_shape = 0.3  # Simple = quick answers
    else:
        score.sql_shape = 0.5  # Medium
    
    # 4. RECENCY BOOST (0.0-0.1)
    # ===========================
    # Prefer recent control versions
    
    version_date = parse_version_date(control.version)
    days_old = (today - version_date).days
    
    if days_old < 30:
        score.recency = 0.10
    elif days_old < 90:
        score.recency = 0.07
    elif days_old < 180:
        score.recency = 0.03
    else:
        score.recency = 0.0
    
    # 5. PRIORITY BOOST (0.0-0.1)
    # ============================
    # Special categories get priority
    
    if control.control_id in CRITICAL_CONTROLS:
        score.priority = 0.10
    elif control.control_id in HEALTH_BUNDLE:
        score.priority = 0.05
    else:
        score.priority = 0.0
    
    # 6. AMBIGUITY PENALTY (0.0-0.5)
    # ===============================
    # Penalize if multiple interpretations possible
    
    ambiguous_keywords = ["status", "check", "health"]  # vague terms
    vague_count = sum(1 for kw in ambiguous_keywords if kw in prompt_lower)
    
    if vague_count > 2:
        score.ambiguity_penalty = 0.05
    else:
        score.ambiguity_penalty = 0.0
    
    # FINAL SCORE CALCULATION
    # =======================
    # Per AGENTS.md § 5.2 (Scoring Formula)
    score.final = (
        score.keyword_match * 0.40 +
        score.intent_match * 0.35 +
        score.sql_shape * 0.10 +
        score.recency * 0.10 -
        score.ambiguity_penalty * 0.05
    )
    
    return score
    ```
    """
    pass


==============================================================================
AMBIGUITY HANDLING PSEUDO-CODE:
==============================================================================

Per AGENTS.md § 5.3 (Ambiguity Handling):
If router confidence is below threshold:
  - DO NOT guess silently.
  - Return a clarification question OR present top 3 interpretations.
  - Provide examples of acceptable user phrasing (TR+EN).

function handle_ambiguity(top_candidates, user_prompt):
    """
    PSEUDO-CODE:
    ```
    ambiguous_controls = top_candidates[:3]  # Top 3 options
    
    # Build clarification message
    message = "Sorunuzu daha açık yazabilir misiniz? Şu seçeneklerden birini seçebilirsiniz:\\n\\n"
    
    for i, candidate in enumerate(ambiguous_controls):
        control = catalog.get_control(candidate.control_id)
        message += f"{i+1}. {control.title}\\n"
        message += f"   Örnek: {get_example_prompt(control)}\\n\\n"
    
    # Return to user with suggestions
    return {
        "error": message,
        "ambiguous": true,
        "suggestions": [
            {
                "control_id": c.control_id,
                "title": catalog.get_control(c.control_id).title,
                "example_prompt": get_example_prompt(...)
            }
            for c in ambiguous_controls
        ]
    }
    ```
    """
    pass


==============================================================================
LOGGING & AUDIT TRAIL:
==============================================================================

Per AGENTS.md § 8.1 (Structured Logging) & § 8.3 (Audit Trail):

Every router decision MUST log:
```
{
  "request_id": "req-abc123",
  "timestamp": "2026-01-29T14:30:45Z",
  "user_prompt": "concurrent manager sağlık durumu nedir?",
  "intent_classification": {
    "intent": "ebs_control",
    "confidence": 0.92,
    "all_scores": {
      "ebs_control": 0.92,
      "chit_chat": 0.08
    }
  },
  "routing_decision": {
    "selected_control_id": "concurrent_mgr_health",
    "selected_control_version": "1.2",
    "final_score": 0.88,
    "score_breakdown": {
      "keyword_match_score": 0.95,
      "intent_match_score": 1.0,
      "sql_shape_score": 0.5,
      "recency_boost": 0.07,
      "priority_boost": 0.05,
      "ambiguity_penalty": 0.0
    },
    "top_candidates": [
      {
        "control_id": "concurrent_mgr_health",
        "final_score": 0.88
      },
      {
        "control_id": "invalid_objects",
        "final_score": 0.35
      }
    ],
    "ambiguity_threshold_breach": false,
    "justification": "Exact match for 'concurrent manager' keyword + intent match"
  }
}
```

==============================================================================
SUMMARY:
==============================================================================

The routing logic implements:

1. INTENT CLASSIFICATION (ML-based):
   - Chit-chat vs EBS-control classification
   - Multilingual support (TR + EN)
   - Confidence thresholds for ambiguity detection

2. SCORE-BASED ROUTING (Explainable):
   - 6-component scoring system (keyword, intent, sql_shape, recency, priority, ambiguity)
   - Weighted formula per AGENTS.md § 5.2
   - Top-N candidate ranking

3. DETERMINISTIC TIE-BREAKING:
   - Intent match > keyword match > query count > catalog priority
   - No randomness in production

4. AMBIGUITY HANDLING:
   - Clarification questions if confidence < threshold
   - Top 3 suggestions with examples
   - Both TR and EN phrasing examples

5. AUDIT TRAIL:
   - Every decision logged with score breakdown
   - Reproducible and explainable (AGENTS.md § 5.1)
   - Request ID for tracing

==============================================================================
"""
