"""
Web layer routes - API endpoints for chat, intent classification, etc.
Per AGENTS.md § 3.1 (Web layer).
"""

from flask import Blueprint, request, jsonify, current_app
import logging
import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def register_routes(app):
    """Register all API routes"""

    @app.route("/api/chat", methods=["POST"])
    def chat():
        """
        Main chat endpoint - FULL INTEGRATION.
        
        Flow:
        1. Intent Classification (ML)
        2. Route to Control (score-based routing)
        3. Execute DB Queries (read-only, sanitized)
        4. Call Ollama for Summary
        5. Return Response
        
        Request JSON:
        {
            "prompt": "concurrent manager sağlık durumu nedir?",
            "session_id": "optional-session-id"
        }
        
        Response JSON:
        {
            "request_id": "req-uuid",
            "intent": "ebs_control",
            "intent_confidence": 0.92,
            "response": "✓ Concurrent Managers: OK...",
            "verdict": "OK",
            "execution_time_ms": 1234
        }
        """
        request_id = str(uuid.uuid4())[:8]
        start_time = datetime.utcnow()

        try:
            # Parse request
            data = request.get_json(force=True)
            user_prompt = data.get("prompt", "").strip()
            session_id = data.get("session_id", "default")

            if not user_prompt:
                return jsonify({
                    "error": "Lütfen bir soru sorun.",
                    "request_id": request_id
                }), 400

            logger.info(f"[{request_id}] Chat request: '{user_prompt[:100]}'")

            # ===== STEP 1: Intent Classification =====
            logger.debug(f"[{request_id}] STEP 1: Starting intent classification")
            intent_classifier = current_app.config.get("intent_classifier")
            if not intent_classifier:
                logger.error(f"[{request_id}] Intent classifier not initialized")
                return _error_response(request_id, "Intent classifier not initialized", 500)

            intent_start = datetime.utcnow()
            intent_result = intent_classifier.classify(user_prompt)
            intent_time_ms = (datetime.utcnow() - intent_start).total_seconds() * 1000
            logger.info(f"[{request_id}] Intent classified: {intent_result.intent} ({intent_result.confidence:.1%}), duration={intent_time_ms:.0f}ms")

            # ===== STEP 2: Routing (if EBS control) =====
            logger.debug(f"[{request_id}] STEP 2: Processing intent={intent_result.intent}")
            if intent_result.intent == "chit_chat":
                # Direct to Ollama for generic response
                logger.debug(f"[{request_id}] Routing chit-chat to generic response")
                response_text = _generate_chit_chat_response(user_prompt)
                
                execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.info(f"[{request_id}] Chit-chat response ready: {len(response_text)} chars, total_time={execution_time_ms:.0f}ms")
                return jsonify({
                    "request_id": request_id,
                    "session_id": session_id,
                    "intent": "chit_chat",
                    "intent_confidence": intent_result.confidence,
                    "response": response_text,
                    "verdict": "OK",
                    "execution_time_ms": execution_time_ms,
                    "timestamp": start_time.isoformat()
                }), 200

            elif intent_result.intent in ["ebs_control", "ambiguous"]:
                # Route to specific control
                router = current_app.config.get("score_based_router")
                catalog = current_app.config.get("control_catalog")
                if not router or not catalog:
                    return _error_response(request_id, "Router or catalog not initialized", 500)

                logger.debug(f"[{request_id}] Routing to control selection (intent={intent_result.intent})")
                router_decision = router.route(user_prompt, intent_result.intent)
                logger.info(
                    f"[{request_id}] Router: selected={router_decision.selected_control_id}, "
                    f"confidence={router_decision.confidence:.3f}, "
                    f"ambiguous={router_decision.ambiguity_threshold_breach}"
                )

                if not router_decision.selected_control_id:
                    # Low confidence, ask clarification
                    logger.warning(
                        f"[{request_id}] Router ambiguous: confidence={router_decision.confidence:.3f}, "
                        f"will ask clarification with {len(router_decision.suggested_interpretations)} suggestions"
                    )
                    response_text = f"Sorunuzu daha net açıklamış olabilir misiniz? Örneğin:\n"
                    for interp in router_decision.suggested_interpretations[:3]:
                        response_text += f"\n- {interp}"
                    
                    execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                    logger.info(f"[{request_id}] Ambiguous response ready: total_time={execution_time_ms:.0f}ms")
                    return jsonify({
                        "request_id": request_id,
                        "session_id": session_id,
                        "intent": "ambiguous",
                        "intent_confidence": intent_result.confidence,
                        "response": response_text,
                        "verdict": "UNKNOWN",
                        "execution_time_ms": execution_time_ms,
                        "timestamp": start_time.isoformat()
                    }), 200

                # ===== STEP 3: DB Query Execution =====
                logger.debug(f"[{request_id}] STEP 3: Starting DB query execution")
                control = catalog.get_control(router_decision.selected_control_id)
                if not control:
                    logger.error(f"[{request_id}] Control not found: {router_decision.selected_control_id}")
                    return _error_response(request_id, f"Control not found: {router_decision.selected_control_id}", 500)

                logger.debug(f"[{request_id}] Control loaded: {control.control_id} v{control.version}")

                executor = current_app.config.get("query_executor")
                if not executor:
                    logger.error(f"[{request_id}] Query executor not initialized")
                    return _error_response(request_id, "Query executor not initialized", 500)

                db_start = datetime.utcnow()
                logger.debug(f"[{request_id}] Executing {len(control.queries)} queries from control")
                
                exec_result = executor.execute_control(control, {})  # No binds for now
                
                db_time_ms = (datetime.utcnow() - db_start).total_seconds() * 1000
                error_count = len([qr for qr in exec_result.query_results if qr.error])
                logger.info(
                    f"[{request_id}] DB execution completed: {len(exec_result.query_results)} query results, "
                    f"total_rows={sum(len(qr.rows) for qr in exec_result.query_results)}, "
                    f"duration={db_time_ms:.0f}ms, errors={error_count}"
                )
                
                if exec_result.has_errors:
                    logger.error(f"[{request_id}] DB execution errors: {exec_result.errors}")
                    return _error_response(request_id, "DB query execution failed", 500)

                # ===== STEP 4: Ollama Summarization =====
                logger.debug(f"[{request_id}] STEP 4: Starting Ollama summarization")
                
                ollama_client = current_app.config.get("ollama_client")
                prompt_builder = current_app.config.get("prompt_builder")
                if not ollama_client or not prompt_builder:
                    logger.error(f"[{request_id}] Ollama client or prompt builder not initialized")
                    return _error_response(request_id, "Ollama client or prompt builder not initialized", 500)

                logger.debug(f"[{request_id}] Building prompts for control: {control.control_id}")
                system_prompt = prompt_builder.build_system_prompt()
                context_prompt = prompt_builder.build_context_prompt(control, exec_result)
                logger.debug(f"[{request_id}] System prompt len={len(system_prompt)}, context len={len(context_prompt)}")
                
                ollama_start = datetime.utcnow()
                logger.debug(f"[{request_id}] Calling Ollama with model={ollama_client.model_name}")
                summary_response = ollama_client.summarize(system_prompt, context_prompt, user_prompt)
                ollama_time_ms = (datetime.utcnow() - ollama_start).total_seconds() * 1000
                
                if not summary_response:
                    logger.warning(f"[{request_id}] Ollama summarization failed/empty, returning fallback summary")
                    summary_response = _generate_fallback_summary(exec_result)
                else:
                    logger.info(
                        f"[{request_id}] Ollama response: verdict={summary_response.verdict}, "
                        f"summary_bullets={len(summary_response.summary_bullets)}, "
                        f"duration={ollama_time_ms:.0f}ms"
                    )

                # ===== STEP 5: Response Formatting =====
                logger.debug(f"[{request_id}] STEP 5: Formatting response")
                response_text = _format_response(summary_response)
                logger.debug(f"[{request_id}] Response formatted: {len(response_text)} chars, verdict={summary_response.verdict}")
                
                execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.info(
                    f"[{request_id}] Chat request completed: "
                    f"intent={intent_result.intent}, "
                    f"control={router_decision.selected_control_id}, "
                    f"verdict={summary_response.verdict}, "
                    f"total_time={execution_time_ms:.0f}ms "
                    f"(intent={intent_time_ms:.0f}ms, db={db_time_ms:.0f}ms, ollama={ollama_time_ms:.0f}ms)"
                )

                return jsonify({
                    "request_id": request_id,
                    "session_id": session_id,
                    "intent": intent_result.intent,
                    "intent_confidence": intent_result.confidence,
                    "selected_control": router_decision.selected_control_id,
                    "response": response_text,
                    "verdict": summary_response.verdict,
                    "execution_time_ms": execution_time_ms,
                    "db_time_ms": db_time_ms,
                    "ollama_time_ms": ollama_time_ms,
                    "timestamp": start_time.isoformat()
                }), 200

            else:
                # Unknown intent
                logger.warning(f"[{request_id}] Unknown intent: {intent_result.intent}")
                response_text = "Sorunuzu tam olarak anlayamadım. EBS ile ilgili bir soru sorabilir misiniz?"
                execution_time_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                logger.info(f"[{request_id}] Unknown intent response ready: total_time={execution_time_ms:.0f}ms")
                return jsonify({
                    "request_id": request_id,
                    "session_id": session_id,
                    "intent": "unknown",
                    "intent_confidence": 0.0,
                    "response": response_text,
                    "verdict": "UNKNOWN",
                    "execution_time_ms": execution_time_ms,
                    "timestamp": start_time.isoformat()
                }), 200

        except Exception as e:
            logger.error(
                f"[{request_id}] Chat request failed: {type(e).__name__}: {e}",
                exc_info=True
            )
            return _error_response(request_id, "İşlem sırasında bir hata oluştu.", 500, str(e))

    @app.route("/api/intent", methods=["POST"])
    def detect_intent():
        """
        Intent detection endpoint (for debugging).
        """
        request_id = str(uuid.uuid4())[:8]
        
        try:
            data = request.get_json(force=True)
            user_prompt = data.get("prompt", "").strip()

            if not user_prompt:
                return jsonify({"error": "Prompt required"}), 400

            classifier = current_app.config.get("intent_classifier")
            if not classifier:
                return jsonify({"error": "Classifier not initialized"}), 500

            result = classifier.classify(user_prompt)
            return jsonify({
                "request_id": request_id,
                "prompt": user_prompt,
                "intent": result.intent,
                "confidence": round(result.confidence, 3),
                "all_scores": {k: round(v, 3) for k, v in result.all_scores.items()}
            }), 200

        except Exception as e:
            logger.error(f"Intent detection error: {e}", exc_info=True)
            return jsonify({"error": str(e), "request_id": request_id}), 500

    @app.route("/api/controls", methods=["GET"])
    def list_controls():
        """List available controls."""
        try:
            catalog = current_app.config.get("control_catalog")
            if not catalog:
                return jsonify({"error": "Catalog not initialized"}), 500

            controls = catalog.get_all_controls()
            control_list = [
                {
                    "control_id": c.control_id,
                    "version": c.version,
                    "title": c.title,
                    "intent": c.intent,
                    "keywords": c.keywords.en[:3] + c.keywords.tr[:3]  # Sample keywords
                }
                for c in controls
            ]
            
            return jsonify({
                "controls": control_list,
                "total": len(control_list)
            }), 200

        except Exception as e:
            logger.error(f"List controls error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @app.route("/api/metrics", methods=["GET"])
    def get_metrics():
        """Return observability metrics (local file for now)."""
        try:
            # TODO: Load from metrics file (metrics.jsonl)
            return jsonify({
                "requests_total": 0,
                "ebs_control_requests": 0,
                "avg_response_time_ms": 0,
                "errors": 0
            }), 200

        except Exception as e:
            logger.error(f"Get metrics error: {e}", exc_info=True)
            return jsonify({"error": str(e)}), 500


# ===== Helper Functions =====

def _error_response(request_id: str, error_msg: str, status: int, details: Optional[str] = None) -> tuple:
    """Return error response JSON"""
    response = {
        "error": error_msg,
        "request_id": request_id,
    }
    if details:
        response["details"] = details
    return jsonify(response), status


def _generate_chit_chat_response(prompt: str) -> str:
    """Generate simple chit-chat response without LLM"""
    if "merhaba" in prompt.lower() or "hello" in prompt.lower():
        return "Merhaba! Ben EBS sistem yöneticisine yardımcı olmak için tasarlanmış bir yapay zekâyım. EBS sisteminde herhangi bir sorunuz var mı?"
    elif "nasılsın" in prompt.lower() or "how are you" in prompt.lower():
        return "İyiyim, teşekkür ederim! EBS sistemine dair sorularınızı yanıtlamak için buradayım."
    elif "teşekkür" in prompt.lower() or "thank" in prompt.lower():
        return "Rica ederim! Başka bir şey ile yardımcı olabilir miyim?"
    else:
        return "Bana EBS sistemi hakkında sorularınızı sorun. Concurrent Manager, Invalid Objects, ADOP durumu veya Workflow hakkında bilgi almak isteyebilirsiniz."


def _generate_fallback_summary(exec_result):
    """Generate fallback summary if Ollama fails"""
    from src.controls.schema import LLMSummaryResponse, LLMOutputVerdictType
    
    bullet_count = sum(len(q.rows) for q in exec_result.query_results if q.rows)
    
    return LLMSummaryResponse(
        summary_bullets=[
            f"{len(exec_result.query_results)} sorgu başarıyla çalıştırıldı.",
            f"Toplam {bullet_count} sonuç alındı.",
        ],
        verdict=LLMOutputVerdictType.UNKNOWN,
        evidence=[
            "Ollama özetleme başarısız, ham veriler yukarıda gösterilmektedir."
        ]
    )


def _format_response(summary_response) -> str:
    """Format LLMSummaryResponse into readable markdown"""
    lines = []
    
    # Verdict as emoji
    verdict_emoji = {
        "OK": "✓",
        "WARN": "⚠️",
        "CRIT": "🔴",
        "UNKNOWN": "❓"
    }
    emoji = verdict_emoji.get(summary_response.verdict, "❓")
    
    lines.append(f"**{emoji} {summary_response.verdict}**\n")
    
    # Summary bullets
    for bullet in summary_response.summary_bullets:
        lines.append(f"- {bullet}")
    
    lines.append("")
    
    # Evidence
    if summary_response.evidence:
        lines.append("**Kanıtlar:**")
        for evidence in summary_response.evidence:
            lines.append(f"- {evidence}")
        lines.append("")
    
    # Details if present
    if summary_response.details:
        lines.append("**Detaylar:**")
        lines.append(summary_response.details)
        lines.append("")
    
    # Next steps if present
    if summary_response.next_checks:
        lines.append("**Önerilen Sonraki Adımlar:**")
        for step in summary_response.next_checks:
            lines.append(f"- {step}")
    
    return "\n".join(lines)
