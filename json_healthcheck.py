#!/usr/bin/env python3
"""
JSON SQL Healthcheck - Control Catalog Validation Tool
Purpose: Verify all SQL statements in control catalog files
         Report syntax errors, invalid table references, etc.
Per AGENTS.md § 4 (Control Catalog Rules): Schema validation
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
import oracledb
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

class ControlCatalogHealthcheck:
    """Validate all SQL queries in control catalog"""

    def __init__(self):
        """Initialize healthcheck with DB connection"""
        self.oracle_user = os.getenv("ORACLE_USER")
        self.oracle_pass = os.getenv("ORACLE_PASS")
        self.oracle_dsn = os.getenv("ORACLE_DSN")
        self.oracle_home = os.getenv("ORACLE_HOME", "/appl01/ebs-insight/instantclient_21_1")
        self.catalog_dir = os.getenv("CATALOG_DIR", "knowledge/controls")
        
        # Validation results
        self.total_controls = 0
        self.total_queries = 0
        self.passed_queries = 0
        self.failed_queries = 0
        self.errors = []
        
        self.pool = None
        self.connection = None

    def connect_db(self):
        """Establish database connection (thick mode, read-only)"""
        try:
            logger.info(f"Initializing Oracle thick mode with {self.oracle_home}...")
            oracledb.init_oracle_client(lib_dir=self.oracle_home)
            
            logger.info(f"Connecting to Oracle EBS R12: {self.oracle_dsn}...")
            self.pool = oracledb.create_pool(
                user=self.oracle_user,
                password=self.oracle_pass,
                dsn=self.oracle_dsn,
                min=1,
                max=1,
                increment=1,
                homogeneous=True,
                threaded=False,
            )
            
            self.connection = self.pool.acquire()
            logger.info("✓ Database connected successfully")
            return True
            
        except Exception as e:
            error_msg = f"✗ Database connection failed: {str(e)}"
            logger.error(error_msg)
            self.errors.append({"type": "CONNECTION", "message": error_msg})
            return False

    def close_db(self):
        """Close database connection"""
        try:
            if self.connection:
                self.connection.close()
            if self.pool:
                self.pool.close()
            logger.info("✓ Database connection closed")
        except Exception as e:
            logger.warning(f"Error closing connection: {e}")

    def load_controls(self) -> list:
        """Load all control JSON files from catalog"""
        controls = []
        
        if not os.path.isdir(self.catalog_dir):
            error_msg = f"✗ Catalog directory not found: {self.catalog_dir}"
            logger.error(error_msg)
            self.errors.append({"type": "CATALOG", "message": error_msg})
            return controls
        
        json_files = list(Path(self.catalog_dir).glob("*.json"))
        logger.info(f"Found {len(json_files)} control files in {self.catalog_dir}")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    control = json.load(f)
                    control['_file'] = str(json_file)
                    controls.append(control)
                logger.info(f"  ✓ Loaded {json_file.name}")
            except json.JSONDecodeError as e:
                error_msg = f"✗ JSON parse error in {json_file.name}: {str(e)}"
                logger.error(error_msg)
                self.errors.append({
                    "file": json_file.name,
                    "type": "JSON_PARSE",
                    "message": error_msg
                })
            except Exception as e:
                error_msg = f"✗ Error loading {json_file.name}: {str(e)}"
                logger.error(error_msg)
                self.errors.append({
                    "file": json_file.name,
                    "type": "LOAD",
                    "message": error_msg
                })
        
        return controls

    def validate_control_schema(self, control: dict, filename: str) -> bool:
        """Validate control has required fields per AGENTS.md § 4.1"""
        required_fields = [
            'control_id', 'version', 'title', 'description',
            'intent', 'keywords', 'queries'
        ]
        
        for field in required_fields:
            if field not in control:
                error_msg = f"✗ Control {filename} missing required field: {field}"
                logger.error(error_msg)
                self.errors.append({
                    "file": filename,
                    "control_id": control.get('control_id', 'UNKNOWN'),
                    "type": "SCHEMA",
                    "message": error_msg
                })
                return False
        
        if not isinstance(control.get('queries'), list) or len(control['queries']) == 0:
            error_msg = f"✗ Control {filename} has no queries"
            logger.warning(error_msg)
            self.errors.append({
                "file": filename,
                "control_id": control.get('control_id', 'UNKNOWN'),
                "type": "SCHEMA",
                "message": error_msg
            })
            return False
        
        return True

    def test_query(self, control_id: str, query_id: str, sql: str, row_limit: int = 1) -> dict:
        """Test single SQL query - execute and catch errors"""
        result = {
            "control_id": control_id,
            "query_id": query_id,
            "status": "FAIL",
            "error": None,
            "rows_returned": 0,
            "duration_ms": 0
        }
        
        if not self.connection:
            result["error"] = "Database not connected"
            return result
        
        # Security check: reject non-SELECT
        if not sql.strip().upper().startswith("SELECT"):
            result["error"] = f"Non-SELECT statement: {sql[:50]}..."
            return result
        
        try:
            import time
            start = time.time()
            
            cursor = self.connection.cursor()
            cursor.arraysize = row_limit
            cursor.execute(sql)
            rows = cursor.fetchall()
            
            duration_ms = int((time.time() - start) * 1000)
            
            cursor.close()
            
            result["status"] = "PASS"
            result["rows_returned"] = len(rows)
            result["duration_ms"] = duration_ms
            self.passed_queries += 1
            
            logger.info(
                f"  ✓ {control_id}.{query_id}: "
                f"OK ({len(rows)} rows, {duration_ms}ms)"
            )
            
        except oracledb.DatabaseError as e:
            error_code = str(e).split(':')[0] if ':' in str(e) else "ORA-UNKNOWN"
            result["error"] = str(e)
            result["status"] = "FAIL"
            self.failed_queries += 1
            
            logger.error(
                f"  ✗ {control_id}.{query_id}: "
                f"{error_code} - {str(e)[:100]}"
            )
            
        except Exception as e:
            result["error"] = str(e)
            result["status"] = "FAIL"
            self.failed_queries += 1
            
            logger.error(
                f"  ✗ {control_id}.{query_id}: "
                f"Unexpected error - {str(e)[:100]}"
            )
        
        return result

    def validate_controls(self, controls: list) -> list:
        """Validate all controls and test their queries"""
        test_results = []
        self.total_controls = len(controls)
        
        for control in controls:
            filename = Path(control.get('_file', 'unknown')).name
            control_id = control.get('control_id', 'UNKNOWN')
            
            logger.info(f"\n[{control_id}] Validating {filename}...")
            
            # Schema validation
            if not self.validate_control_schema(control, filename):
                continue
            
            # Query validation
            queries = control.get('queries', [])
            for query_def in queries:
                query_id = query_def.get('query_id', 'UNKNOWN')
                sql = query_def.get('sql', '').strip()
                
                if not sql:
                    error_msg = f"✗ {control_id}.{query_id} has empty SQL"
                    logger.error(f"  {error_msg}")
                    self.errors.append({
                        "file": filename,
                        "control_id": control_id,
                        "query_id": query_id,
                        "type": "EMPTY_SQL",
                        "message": error_msg
                    })
                    self.failed_queries += 1
                    continue
                
                self.total_queries += 1
                
                if self.connection:
                    result = self.test_query(control_id, query_id, sql)
                    test_results.append(result)
                    
                    if result["status"] == "FAIL":
                        self.errors.append({
                            "file": filename,
                            "control_id": control_id,
                            "query_id": query_id,
                            "type": "SQL_ERROR",
                            "message": result["error"],
                            "sql_preview": sql[:100]
                        })
        
        return test_results

    def generate_report(self, test_results: list) -> str:
        """Generate healthcheck report"""
        report = []
        report.append("\n" + "="*80)
        report.append("CONTROL CATALOG HEALTHCHECK REPORT")
        report.append("="*80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append(f"Catalog Directory: {self.catalog_dir}\n")
        
        # Summary
        report.append("[SUMMARY]")
        report.append(f"Total Controls: {self.total_controls}")
        report.append(f"Total Queries: {self.total_queries}")
        report.append(f"Passed: {self.passed_queries} ✓")
        report.append(f"Failed: {self.failed_queries} ✗")
        
        if self.total_queries > 0:
            pass_rate = (self.passed_queries / self.total_queries) * 100
            report.append(f"Pass Rate: {pass_rate:.1f}%\n")
        
        # Errors detail
        if self.errors:
            report.append("[ERRORS FOUND]")
            
            # Group by type
            errors_by_type = {}
            for error in self.errors:
                etype = error.get('type', 'UNKNOWN')
                if etype not in errors_by_type:
                    errors_by_type[etype] = []
                errors_by_type[etype].append(error)
            
            for etype, type_errors in sorted(errors_by_type.items()):
                report.append(f"\n{etype} ({len(type_errors)} errors):")
                for error in type_errors[:10]:  # Limit to 10 per type
                    control_id = error.get('control_id', 'N/A')
                    query_id = error.get('query_id', 'N/A')
                    msg = error.get('message', 'No message')
                    
                    if control_id != 'N/A' and query_id != 'N/A':
                        report.append(f"  • [{control_id}.{query_id}] {msg}")
                    elif control_id != 'N/A':
                        report.append(f"  • [{control_id}] {msg}")
                    else:
                        report.append(f"  • {msg}")
                
                if len(type_errors) > 10:
                    report.append(f"  ... and {len(type_errors) - 10} more")
        else:
            report.append("\n[RESULT] ✓ All checks passed!")
        
        report.append("\n" + "="*80 + "\n")
        
        return "\n".join(report)

    def run(self) -> int:
        """Run full healthcheck"""
        logger.info("Starting Control Catalog Healthcheck...")
        
        # Load controls
        controls = self.load_controls()
        if not controls:
            logger.error("No controls loaded, cannot proceed")
            return 1
        
        # Connect to DB
        if not self.connect_db():
            logger.warning("Continuing healthcheck without database validation...")
        
        try:
            # Validate controls
            test_results = self.validate_controls(controls)
            
            # Generate report
            report = self.generate_report(test_results)
            print(report)
            
            # Save report
            report_file = "healthcheck_report.txt"
            with open(report_file, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"Report saved to {report_file}")
            
            # Return exit code based on failures
            return 1 if self.failed_queries > 0 else 0
            
        finally:
            self.close_db()


if __name__ == "__main__":
    healthcheck = ControlCatalogHealthcheck()
    exit_code = healthcheck.run()
    sys.exit(exit_code)
