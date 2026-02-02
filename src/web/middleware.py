"""
Web middleware - error handling, logging, request processing.
Per AGENTS.md § 3.1 (Web layer).
Per SECURITY.MD § 5.3 (Rate Limiting).
"""

from flask import Flask, request, g, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import logging
import time
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)

# Global rate limiter instance
limiter = None


def setup_rate_limiter(app: Flask) -> Limiter:
    """
    Setup rate limiting per SECURITY.MD § 5.3.
    
    Limits:
    - 10 requests per minute (per IP)
    - 100 requests per hour (per IP)
    
    Returns:
        Limiter instance
    """
    global limiter
    
    limiter = Limiter(
        app=app,
        key_func=get_remote_address,  # Rate limit by IP address
        default_limits=["100 per hour", "10 per minute"],
        storage_uri="memory://",  # In-memory storage (simple, fast)
        strategy="fixed-window",
    )
    
    logger.info("✓ Rate limiter initialized: 10/min, 100/hour per IP")
    return limiter


def setup_middleware(app: Flask):
    """Setup Flask middleware"""

    @app.before_request
    def before_request():
        """Track request timing and assign request ID"""
        g.request_id = str(uuid.uuid4())[:8]
        g.start_time = time.time()
        
        # Log request
        logger.info(
            f"[{g.request_id}] {request.method} {request.path} "
            f"from {request.remote_addr}"
        )

    @app.after_request
    def after_request(response):
        """Log response and timing"""
        elapsed_ms = (time.time() - g.start_time) * 1000
        
        logger.info(
            f"[{g.request_id}] {response.status_code} "
            f"in {elapsed_ms:.2f}ms"
        )
        
        # Add request ID to response headers
        response.headers["X-Request-ID"] = g.request_id
        
        return response

    @app.errorhandler(400)
    def bad_request(e):
        """Handle bad request"""
        return jsonify({
            "error": "Hatalı istek",
            "request_id": g.get("request_id", "unknown"),
            "details": str(e)
        }), 400

    @app.errorhandler(405)
    def method_not_allowed(e):
        """Handle method not allowed"""
        return jsonify({
            "error": "Method not allowed",
            "request_id": g.get("request_id", "unknown")
        }), 405

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        """
        Handle rate limit exceeded.
        Per SECURITY.MD § 5.3 (Rate Limiting).
        """
        request_id = g.get("request_id", "unknown")
        client_ip = request.remote_addr
        
        # Security audit log
        logger.warning(
            f"[{request_id}] RATE LIMIT EXCEEDED: {client_ip} - {request.path}"
        )
        
        return jsonify({
            "error": "Çok fazla istek gönderdiniz. Lütfen biraz bekleyin.",
            "request_id": request_id,
            "rate_limit": "10 requests/minute, 100 requests/hour",
            "retry_after": e.description if hasattr(e, 'description') else "60 seconds"
        }), 429
