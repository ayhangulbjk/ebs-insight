"""
Flask application factory and entry point.
Per AGENTS.md § 1.2 fail-fast config validation.
"""

import os
import sys
from pathlib import Path

# Ensure src is in path
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, render_template, jsonify
from flask_cors import CORS
import logging

from src.config import load_config, ConfigValidationError
from src.web.middleware import setup_middleware
from src.web.routes import register_routes
from src.observability.logger import setup_logging

logger = logging.getLogger(__name__)


def create_app(env_file: str = None) -> Flask:
    """
    Flask application factory with fail-fast config validation.
    
    Args:
        env_file: Path to .env file (optional)
        
    Returns:
        Flask: Configured Flask application
        
    Raises:
        ConfigValidationError: If config validation fails (app refuses to start)
    """
    
    # === 1. FAIL-FAST CONFIG VALIDATION ===
    try:
        config = load_config(env_file=env_file)
        logger.info("✓ Configuration validation passed")
    except ConfigValidationError as e:
        logger.error(f"Configuration validation failed:\n{e}")
        sys.exit(1)

    # === 2. CREATE FLASK APP ===
    app = Flask(
        __name__,
        static_folder=Path(__file__).parent / "static",
        template_folder=Path(__file__).parent / "templates",
    )
    
    app.config["JSON_SORT_KEYS"] = False
    app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB max request
    
    # Store config in app context
    app.config["EBS_CONFIG"] = config
    
    # === 3. SETUP LOGGING ===
    setup_logging(app)

    # === 4. SETUP CORS ===
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logger.info("✓ CORS enabled")

    # === 5. SETUP MIDDLEWARE ===
    setup_middleware(app)
    logger.info("✓ Middleware registered")

    # === 5b. SETUP RATE LIMITING ===
    # Per SECURITY.MD § 5.3 (Rate Limiting)
    from src.web.middleware import setup_rate_limiter
    try:
        rate_limiter = setup_rate_limiter(app)
        app.config["rate_limiter"] = rate_limiter
    except Exception as e:
        logger.error(f"Rate limiter setup failed: {e}")
        sys.exit(1)

    # === 6. INITIALIZE SYSTEM COMPONENTS ===
    # 6a. Load control catalog
    from src.controls.loader import ControlCatalog
    try:
        catalog = ControlCatalog(config.catalog_dir)
        logger.info(f"✓ Control catalog loaded: {len(catalog.get_all_controls())} controls")
        app.config["control_catalog"] = catalog
    except Exception as e:
        logger.error(f"Catalog loading failed: {e}")
        sys.exit(1)

    # 6b. Initialize intent classifier
    from src.intent.classifier import IntentClassifier
    try:
        classifier = IntentClassifier(catalog)
        logger.info("✓ Intent classifier initialized (Naive Bayes + TF-IDF)")
        app.config["intent_classifier"] = classifier
    except Exception as e:
        logger.error(f"Intent classifier initialization failed: {e}")
        sys.exit(1)

    # 6c. Initialize score-based router
    from src.intent.router import ScoreBasedRouter
    try:
        router = ScoreBasedRouter(catalog)
        logger.info("✓ Score-based router initialized")
        app.config["score_based_router"] = router
    except Exception as e:
        logger.error(f"Router initialization failed: {e}")
        sys.exit(1)

    # 6d. Initialize DB connection pool
    from src.db.connection import DBConnectionPool
    try:
        db_pool = DBConnectionPool(config)
        if not db_pool.verify_connectivity():
            logger.error("DB connectivity verification failed")
            sys.exit(1)
        logger.info("✓ DB connection pool initialized (thick mode, pool size 10)")
        app.config["db_pool"] = db_pool
    except Exception as e:
        logger.error(f"DB pool initialization failed: {e}")
        sys.exit(1)

    # 6e. Initialize query executor
    from src.db.executor import QueryExecutor
    try:
        executor = QueryExecutor(db_pool)
        logger.info("✓ Query executor initialized (read-only enforced, sanitization enabled)")
        app.config["query_executor"] = executor
    except Exception as e:
        logger.error(f"Query executor initialization failed: {e}")
        sys.exit(1)

    # 6f. Initialize Ollama client
    from src.llm.client import OllamaClient
    try:
        ollama_client = OllamaClient(config.ollama_url, config.ollama_model)
        if not ollama_client.verify_connectivity():
            logger.error("Ollama connectivity verification failed")
            sys.exit(1)
        logger.info(f"✓ Ollama client initialized: {config.ollama_model}")
        app.config["ollama_client"] = ollama_client
    except Exception as e:
        logger.error(f"Ollama client initialization failed: {e}")
        sys.exit(1)

    # 6g. Initialize prompt builder
    from src.llm.prompt_builder import PromptBuilder
    try:
        prompt_builder = PromptBuilder()
        logger.info("✓ Prompt builder initialized")
        app.config["prompt_builder"] = prompt_builder
    except Exception as e:
        logger.error(f"Prompt builder initialization failed: {e}")
        sys.exit(1)

    # === 7. REGISTER ROUTES ===
    register_routes(app)
    logger.info("✓ Routes registered")

    # === 8. HEALTH CHECK ENDPOINT ===
    @app.route("/health", methods=["GET"])
    def health():
        """Health check endpoint"""
        return jsonify({
            "status": "ok",
            "version": "0.1.0",
            "oracle": config.oracle_dsn,
            "ollama": config.ollama_model,
            "controls": len(catalog.get_all_controls()),
        }), 200

    # === 9. STATIC PAGES ===
    @app.route("/", methods=["GET"])
    def index():
        """Main chat UI"""
        return render_template("chat.html")

    # === 10. ERROR HANDLERS ===
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Not found"}), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Internal server error: {e}")
        return jsonify({"error": "Internal server error"}), 500

    logger.info(f"✓ Flask app initialized: {app.name}")
    return app


if __name__ == "__main__":
    app = create_app()
    
    logger.info("=" * 60)
    logger.info("EBS-Insight Chat Application")
    logger.info("=" * 60)
    logger.info("Starting Flask development server...")
    logger.info("Access at: http://127.0.0.1:5000")
    logger.info("=" * 60)
    
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,
        use_reloader=True,
    )
