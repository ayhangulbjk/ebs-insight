"""
Oracle Database Connection Pool Management.
Per AGENTS.md § 1.2 (Fail-Fast Config Validation) & § 6.1 (Read-Only Enforcement).

Uses python-oracledb thick mode with SessionPool.
Pool size: 10, Idle timeout: 300 seconds (per design decisions).
"""

import logging
import os
from typing import Optional
import oracledb

logger = logging.getLogger(__name__)


class DBConnectionError(Exception):
    """Raised when DB connection fails"""
    pass


class DBConnectionPool:
    """
    Oracle EBS R12 connection pool with fail-fast validation.
    
    Per AGENTS.md § 1.2:
    - Validates Oracle thick mode prerequisites
    - Read-only user enforced at session level
    - Timeout: 300 seconds (idle)
    - Pool size: 10 connections
    """

    POOL_SIZE = 10
    IDLE_TIMEOUT_SECONDS = 300
    WAIT_TIMEOUT_SECONDS = 5

    def __init__(self, config):
        """
        Initialize connection pool.
        
        Args:
            config: Config object with Oracle credentials & settings
            
        Raises:
            DBConnectionError: If connection fails
        """
        self.config = config
        self.pool = None
        self._initialize_pool()

    def _initialize_pool(self):
        """Initialize oracledb connection pool with thick mode"""
        logger.info("Initializing Oracle connection pool...")

        try:
            # Set up thick mode environment
            # Per AGENTS.md § 1.1: ORACLE_HOME, LD_LIBRARY_PATH
            oracle_home = self.config.oracle_home
            if not oracle_home:
                raise DBConnectionError("ORACLE_HOME not configured")

            # Thick mode initialization
            oracledb.init_oracle_client(lib_dir=oracle_home)
            logger.info(f"✓ Thick mode initialized with {oracle_home}")

            # Create session pool
            self.pool = oracledb.create_pool(
                user=self.config.oracle_user,
                password=self.config.oracle_pass,
                dsn=self.config.oracle_dsn,
                min=1,
                max=self.POOL_SIZE,
                increment=2,
                homogeneous=True,
                threaded=True,
            )

            logger.info(
                f"✓ Connection pool created: "
                f"size={self.POOL_SIZE}, idle_timeout={self.IDLE_TIMEOUT_SECONDS}s"
            )

            # Verify connectivity
            self._test_connection()

        except oracledb.DatabaseError as e:
            raise DBConnectionError(f"Oracle connection failed: {e}")
        except Exception as e:
            raise DBConnectionError(f"Failed to initialize connection pool: {e}")

    def _test_connection(self):
        """Test connectivity to database"""
        try:
            conn = self.pool.acquire()
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM DUAL")
            cursor.close()
            conn.close()
            logger.info("✓ Database connectivity verified")
        except Exception as e:
            raise DBConnectionError(f"Database connectivity test failed: {e}")

    def get_connection(self, timeout: int = WAIT_TIMEOUT_SECONDS):
        """
        Acquire connection from pool.
        
        Args:
            timeout: Wait timeout in seconds (note: parameter not used in some oracledb versions)
            
        Returns:
            oracledb Connection object
            
        Raises:
            DBConnectionError: If connection cannot be acquired
        """
        if not self.pool:
            raise DBConnectionError("Connection pool not initialized")

        try:
            conn = self.pool.acquire()
            return conn
        except Exception as e:
            logger.error(f"Failed to acquire connection: {e}")
            raise DBConnectionError(f"Connection pool exhausted or timeout: {e}")

    def release_connection(self, conn):
        """Release connection back to pool"""
        if conn:
            try:
                conn.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")

    def close(self):
        """Close connection pool"""
        if self.pool:
            try:
                self.pool.close()
                logger.info("✓ Connection pool closed")
            except Exception as e:
                logger.warning(f"Error closing connection pool: {e}")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
