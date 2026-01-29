"""
Structured logging setup.
Per AGENTS.md § 8.1 (Structured Logging).
"""

import logging
import json
from datetime import datetime
from pythonjsonlogger import jsonlogger
from flask import Flask


def setup_logging(app: Flask):
    """Setup structured JSON logging"""
    
    # Console handler with JSON format
    console_handler = logging.StreamHandler()
    json_formatter = jsonlogger.JsonFormatter()
    console_handler.setFormatter(json_formatter)
    
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    
    # File handler (optional, for metrics)
    try:
        file_handler = logging.FileHandler("logs/app.log")
        file_handler.setFormatter(json_formatter)
        root_logger.addHandler(file_handler)
    except FileNotFoundError:
        pass  # logs/ might not exist yet
