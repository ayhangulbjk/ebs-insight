"""
Web middleware - error handling, logging, request processing.
Per AGENTS.md § 3.1 (Web layer).
"""

from flask import Flask, request, g, jsonify
from functools import wraps
import logging
import time
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


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
