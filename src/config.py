"""
Configuration loader with fail-fast validation.
Per AGENTS.md § 1 (Runtime SSOT & § 1.2 Fail-Fast Config Validation).

If any validation fails → app refuses to start with clear error.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
import logging

# Configure logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ConfigValidationError(Exception):
    """Raised when config validation fails (fail-fast)"""
    pass


class Config:
    """
    Central configuration with fail-fast validation.
    
    Validates:
    1. Oracle thick mode prerequisites (ORACLE_HOME, LD_LIBRARY_PATH, client libs)
    2. DB credentials present (not printed)
    3. Ollama reachable (OLLAMA_URL) and model name configured
    4. Catalog directory exists and validates schema
    
    On failure: raises ConfigValidationError and refuses to proceed.
    """

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize config with fail-fast validation.
        
        Args:
            env_file: Path to .env file (default: .env in project root)
            
        Raises:
            ConfigValidationError: If any required validation fails
        """
        self.errors = []

        # Load .env file
        if env_file:
            load_dotenv(env_file)
        else:
            # Default: look for .env in project root
            env_path = Path(__file__).parent.parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"Loaded .env from {env_path}")

        # === 1. Oracle Configuration ===
        self._validate_oracle_config()

        # === 2. Database Credentials ===
        self._validate_db_credentials()

        # === 3. Ollama Configuration ===
        self._validate_ollama_config()

        # === 4. Catalog Configuration ===
        self._validate_catalog_config()

        # === Fail-Fast: Report all errors ===
        if self.errors:
            error_report = "\n".join(f"  ✗ {err}" for err in self.errors)
            msg = f"Configuration validation failed:\n{error_report}"
            logger.error(msg)
            raise ConfigValidationError(msg)

        logger.info("✓ Configuration validation passed")

    def _validate_oracle_config(self):
        """Validate Oracle thick mode prerequisites per AGENTS.md § 1.1"""
        logger.info("Validating Oracle thick mode prerequisites...")

        # ORACLE_HOME must be set
        self.oracle_home = os.getenv("ORACLE_HOME")
        if not self.oracle_home:
            self.errors.append(
                "ORACLE_HOME env var not set. Required for Oracle thick mode."
            )
            return

        oracle_home_path = Path(self.oracle_home)
        if not oracle_home_path.exists():
            self.errors.append(
                f"ORACLE_HOME directory does not exist: {self.oracle_home}"
            )
            return

        logger.info(f"  ORACLE_HOME: {self.oracle_home}")

        # Check for basic Oracle client libraries
        # (On Linux: libclntsh.so, on Windows: oci.dll or msvcr120.dll)
        expected_libs = ["libclntsh.so", "oci.dll", "msvcr120.dll"]
        found_libs = []
        for lib in expected_libs:
            lib_path = oracle_home_path / lib
            if lib_path.exists():
                found_libs.append(lib)

        if not found_libs:
            self.errors.append(
                f"No Oracle client libraries found in {self.oracle_home}. "
                f"Expected one of: {', '.join(expected_libs)}"
            )
            return

        logger.info(f"  Oracle client library: {found_libs[0]}")

        # LD_LIBRARY_PATH should include ORACLE_HOME (on Linux)
        if sys.platform != "win32":
            ld_library_path = os.getenv("LD_LIBRARY_PATH", "")
            if self.oracle_home not in ld_library_path:
                logger.warning(
                    f"LD_LIBRARY_PATH does not include ORACLE_HOME. "
                    f"May cause runtime issues. Set: export LD_LIBRARY_PATH={self.oracle_home}:$LD_LIBRARY_PATH"
                )

    def _validate_db_credentials(self):
        """Validate DB credentials present (but don't print them) per AGENTS.md § 1.1"""
        logger.info("Validating database credentials...")

        self.oracle_user = os.getenv("ORACLE_USER")
        if not self.oracle_user:
            self.errors.append("ORACLE_USER env var not set")
            return

        self.oracle_pass = os.getenv("ORACLE_PASS")
        if not self.oracle_pass:
            self.errors.append("ORACLE_PASS env var not set")
            return

        self.oracle_dsn = os.getenv("ORACLE_DSN")
        if not self.oracle_dsn:
            self.errors.append("ORACLE_DSN env var not set")
            return

        logger.info(f"  ORACLE_USER: {self.oracle_user} (configured)")
        logger.info(f"  ORACLE_DSN: {self.oracle_dsn} (configured)")
        logger.info("  ORACLE_PASS: *** (configured, not printed)")

    def _validate_ollama_config(self):
        """Validate Ollama reachable and model configured per AGENTS.md § 1.1"""
        logger.info("Validating Ollama configuration...")

        self.ollama_url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.ollama_model = os.getenv("OLLAMA_MODEL")

        if not self.ollama_model:
            self.errors.append("OLLAMA_MODEL env var not set (e.g., ebs-qwen25chat:latest)")
            return

        logger.info(f"  OLLAMA_URL: {self.ollama_url}")
        logger.info(f"  OLLAMA_MODEL: {self.ollama_model}")

        # Check Ollama connectivity (basic health check)
        try:
            import requests

            timeout = 5
            health_url = f"{self.ollama_url}/api/tags"
            logger.info(f"  Checking Ollama connectivity to {health_url}...")
            resp = requests.get(health_url, timeout=timeout)

            if resp.status_code != 200:
                self.errors.append(
                    f"Ollama health check failed: HTTP {resp.status_code} from {self.ollama_url}"
                )
                return

            # Verify model is loaded
            data = resp.json()
            loaded_models = [m.get("name") for m in data.get("models", [])]
            
            if self.ollama_model not in loaded_models:
                self.errors.append(
                    f"Ollama model '{self.ollama_model}' not loaded. "
                    f"Available: {', '.join(loaded_models) if loaded_models else 'none'}"
                )
                return

            logger.info(f"  ✓ Ollama reachable, model '{self.ollama_model}' loaded")

        except ImportError:
            logger.warning("  'requests' package not installed, skipping Ollama connectivity check")
        except Exception as e:
            self.errors.append(f"Failed to connect to Ollama: {e}")
            return

    def _validate_catalog_config(self):
        """Validate catalog directory exists and loads successfully per AGENTS.md § 1.1"""
        logger.info("Validating control catalog...")

        self.catalog_dir = os.getenv("CATALOG_DIR", "./knowledge/controls")
        catalog_path = Path(self.catalog_dir)

        if not catalog_path.exists():
            self.errors.append(
                f"CATALOG_DIR does not exist: {self.catalog_dir}"
            )
            return

        logger.info(f"  CATALOG_DIR: {self.catalog_dir}")

        # Check for at least one control file (JSON or YAML)
        control_files = list(catalog_path.glob("*.json")) + list(catalog_path.glob("*.yaml"))
        if not control_files:
            self.errors.append(
                f"No control files (*.json or *.yaml) found in {self.catalog_dir}"
            )
            return

        logger.info(f"  Found {len(control_files)} control file(s)")

        # Try to load metadata.json if present
        metadata_file = catalog_path / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, "r") as f:
                    self.catalog_metadata = json.load(f)
                logger.info(f"  Catalog metadata: version {self.catalog_metadata.get('version', 'N/A')}")
            except Exception as e:
                logger.warning(f"  Failed to load catalog metadata: {e}")
                self.catalog_metadata = {}
        else:
            self.catalog_metadata = {}

    def get_db_connection_params(self) -> dict:
        """Return DB connection parameters (safe for logging)"""
        return {
            "user": self.oracle_user,
            "dsn": self.oracle_dsn,
        }

    def __repr__(self) -> str:
        return (
            f"Config(\n"
            f"  oracle_home={self.oracle_home},\n"
            f"  oracle_user={self.oracle_user},\n"
            f"  oracle_dsn={self.oracle_dsn},\n"
            f"  ollama_url={self.ollama_url},\n"
            f"  ollama_model={self.ollama_model},\n"
            f"  catalog_dir={self.catalog_dir}\n"
            f")"
        )


def load_config(env_file: Optional[str] = None) -> Config:
    """
    Load and validate config with fail-fast behavior.
    
    Returns:
        Config: Validated configuration object
        
    Raises:
        ConfigValidationError: If any validation fails
    """
    return Config(env_file=env_file)
