"""
Control catalog loader and validator.
Per AGENTS.md § 4 (Control Catalog Rules).
"""

import json
from pathlib import Path
from typing import Dict, List, Optional
import logging
from pydantic import ValidationError

from src.controls.schema import ControlDefinition, ControlCatalog

logger = logging.getLogger(__name__)


class CatalogLoadError(Exception):
    """Raised when catalog loading/validation fails"""
    pass


class ControlCatalog:
    """
    In-memory control catalog with validation.
    Loads all control files from CATALOG_DIR and validates against Pydantic schema.
    """

    def __init__(self, catalog_dir: str):
        """
        Load and validate catalog.
        
        Args:
            catalog_dir: Path to controls directory
            
        Raises:
            CatalogLoadError: If loading or validation fails
        """
        self.catalog_dir = Path(catalog_dir)
        self.controls: Dict[str, ControlDefinition] = {}
        self.metadata: Dict = {}

        self._load_catalog()

    def _load_catalog(self):
        """Load all control files from catalog directory"""
        logger.info(f"Loading control catalog from {self.catalog_dir}...")

        if not self.catalog_dir.exists():
            raise CatalogLoadError(f"Catalog directory not found: {self.catalog_dir}")

        # Load metadata if present
        metadata_file = self.catalog_dir / "metadata.json"
        if metadata_file.exists():
            try:
                with open(metadata_file, "r", encoding="utf-8") as f:
                    self.metadata = json.load(f)
                logger.info(f"Loaded catalog metadata: version {self.metadata.get('metadata', {}).get('version', 'N/A')}")
            except Exception as e:
                logger.warning(f"Failed to load metadata.json: {e}")
                self.metadata = {}

        # Load individual control files
        control_files = sorted(self.catalog_dir.glob("*.json"))
        control_files = [f for f in control_files if f.name != "metadata.json"]

        if not control_files:
            raise CatalogLoadError(f"No control files found in {self.catalog_dir}")

        loaded_count = 0
        errors = []

        for control_file in control_files:
            try:
                with open(control_file, "r", encoding="utf-8") as f:
                    control_data = json.load(f)

                # Validate against Pydantic schema
                control_obj = ControlDefinition(**control_data)
                self.controls[control_obj.control_id] = control_obj
                loaded_count += 1
                logger.info(f"  ✓ Loaded: {control_obj.control_id} (v{control_obj.version})")

            except json.JSONDecodeError as e:
                errors.append(f"JSON parse error in {control_file.name}: {e}")
            except ValidationError as e:
                errors.append(f"Validation error in {control_file.name}: {e}")
            except Exception as e:
                errors.append(f"Error loading {control_file.name}: {e}")

        if errors:
            error_msg = "\n".join(errors)
            raise CatalogLoadError(f"Catalog validation failed:\n{error_msg}")

        logger.info(f"✓ Catalog loaded: {loaded_count} controls")

    def get_control(self, control_id: str) -> Optional[ControlDefinition]:
        """Get a control by ID"""
        return self.controls.get(control_id)

    def get_all_controls(self) -> List[ControlDefinition]:
        """Get all controls"""
        return list(self.controls.values())

    def get_controls_by_intent(self, intent: str) -> List[ControlDefinition]:
        """Get all controls for a specific intent"""
        return [c for c in self.controls.values() if c.intent.value == intent]

    def search_by_keyword(self, keyword: str) -> List[ControlDefinition]:
        """Search controls by keyword (case-insensitive, checks both EN and TR)"""
        keyword_lower = keyword.lower()
        results = []

        for control in self.controls.values():
            # Check English keywords
            en_match = any(
                keyword_lower in kw.lower() or kw.lower() in keyword_lower
                for kw in control.keywords.en
            )
            # Check Turkish keywords
            tr_match = any(
                keyword_lower in kw.lower() or kw.lower() in keyword_lower
                for kw in control.keywords.tr
            )

            if en_match or tr_match:
                results.append(control)

        return results

    def validate_all_controls(self) -> List[str]:
        """
        Validate all loaded controls and return list of issues (if any).
        
        Returns:
            List of validation error messages
        """
        issues = []

        # Check for unique control IDs
        ids = [c.control_id for c in self.controls.values()]
        if len(ids) != len(set(ids)):
            issues.append("Duplicate control_id values detected")

        # Check each control has at least one query
        for control in self.controls.values():
            if not control.queries:
                issues.append(f"Control {control.control_id} has no queries")

            # Check each query has result_schema
            for query in control.queries:
                if not query.result_schema:
                    issues.append(
                        f"Control {control.control_id}, query {query.query_id} has no result_schema"
                    )

        return issues

    def __repr__(self) -> str:
        return (
            f"ControlCatalog(\n"
            f"  directory={self.catalog_dir},\n"
            f"  controls={len(self.controls)},\n"
            f"  control_ids={list(self.controls.keys())}\n"
            f")"
        )


def load_catalog(catalog_dir: str) -> ControlCatalog:
    """
    Load and validate control catalog.
    
    Args:
        catalog_dir: Path to controls directory
        
    Returns:
        ControlCatalog: Loaded and validated catalog
        
    Raises:
        CatalogLoadError: If loading or validation fails
    """
    return ControlCatalog(catalog_dir)
