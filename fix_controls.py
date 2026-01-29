#!/usr/bin/env python3
"""
Fix all Oracle EBS R12 control JSON files for Pydantic schema validation.
Converts keywords arrays to objects with 'en'/'tr' keys.
Converts result_schema arrays to object arrays with name/type/sensitive fields.
Remaps invalid intent values to supported ones.
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, List, Tuple

# Intent mapping as per requirements
INTENT_MAPPING = {
    "session_analysis": "performance",
    "storage": "performance",
    "locks": "performance",
    "parameters": "performance",
    "users": "performance",
    "patches": "performance",
    "database_health": "performance",
    "security": "performance",
    # Keep these as-is
    "data_integrity": "data_integrity",
    "invalid_objects": "invalid_objects",
    "conc_mgr": "conc_mgr",
    "workflow": "workflow",
    "adop": "adop",
}

# Valid intent values
VALID_INTENTS = {"conc_mgr", "workflow", "adop", "invalid_objects", "data_integrity", "performance"}

def infer_column_type(col_name: str) -> str:
    """
    Infer column type based on column name.
    - Columns with TIMESTAMP, DATE, _DATE suffixes → type: DATE
    - Columns with #, _COUNT, _WAITS, _SIZE, _MB, _GB, _BLOCKS, NUM_, PCT_ → type: NUMBER
    - Everything else → type: VARCHAR2
    """
    col_upper = col_name.upper()
    
    # DATE columns
    if "TIMESTAMP" in col_upper or "DATE" in col_upper or col_upper.endswith("_DATE"):
        return "DATE"
    
    # NUMBER columns
    if any(marker in col_upper for marker in ["#", "_COUNT", "_WAITS", "_SIZE", "_MB", "_GB", "_BLOCKS", "NUM_", "PCT_"]):
        return "NUMBER"
    
    return "VARCHAR2"

def is_sensitive(col_name: str) -> bool:
    """
    Mark column as sensitive if it contains user/security-related terms.
    """
    col_upper = col_name.upper()
    sensitive_keywords = ["USERNAME", "OSUSER", "EMAIL", "USER_NAME", "PASSWORD", "GRANTEE", "OS_USER", "ORACLE_USER"]
    return any(keyword in col_upper for keyword in sensitive_keywords)

def convert_keywords(keywords_list: List[str]) -> Dict[str, List[str]]:
    """
    Convert simple array of keywords to object with 'en' and 'tr' keys.
    Simple heuristic: keywords containing Turkish characters go to 'tr', others to 'en'.
    """
    turkish_chars = set("çğıöşüÇĞİÖŞÜ")
    
    en_keywords = []
    tr_keywords = []
    
    for kw in keywords_list:
        if any(c in kw for c in turkish_chars):
            tr_keywords.append(kw)
        else:
            # If it looks like a common English keyword or acronym, add to EN
            en_keywords.append(kw)
    
    # Ensure both lists are non-empty for consistency
    if not en_keywords:
        en_keywords = [keywords_list[0]]
    if not tr_keywords:
        tr_keywords = [keywords_list[-1] if keywords_list else "keyword"]
    
    return {"en": en_keywords, "tr": tr_keywords}

def convert_result_schema(schema_list: List[str]) -> List[Dict[str, Any]]:
    """
    Convert simple string array of column names to object array with type/sensitive fields.
    """
    result = []
    for col_name in schema_list:
        col_type = infer_column_type(col_name)
        sensitive = is_sensitive(col_name)
        result.append({
            "name": col_name,
            "type": col_type,
            "sensitive": sensitive
        })
    return result

def fix_control_file(file_path: Path) -> Tuple[bool, str, Dict[str, int]]:
    """
    Fix a single control file.
    Returns: (success, error_message, fix_counts)
    """
    fix_counts = {
        "keywords_fixed": 0,
        "result_schema_fixed": 0,
        "intent_remapped": 0
    }
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Fix keywords
        if "keywords" in data:
            if isinstance(data["keywords"], list):
                data["keywords"] = convert_keywords(data["keywords"])
                fix_counts["keywords_fixed"] += 1
        
        # Fix intent
        if "intent" in data:
            old_intent = data["intent"]
            if old_intent in INTENT_MAPPING:
                data["intent"] = INTENT_MAPPING[old_intent]
                if INTENT_MAPPING[old_intent] != old_intent:
                    fix_counts["intent_remapped"] += 1
            elif data["intent"] not in VALID_INTENTS:
                # Default to performance if unknown
                data["intent"] = "performance"
                fix_counts["intent_remapped"] += 1
        
        # Fix result_schema in queries
        if "queries" in data and isinstance(data["queries"], list):
            for query in data["queries"]:
                if "result_schema" in query:
                    if isinstance(query["result_schema"], list):
                        # Check if it's a list of strings (old format)
                        if query["result_schema"] and isinstance(query["result_schema"][0], str):
                            query["result_schema"] = convert_result_schema(query["result_schema"])
                            fix_counts["result_schema_fixed"] += 1
        
        # Write back
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return True, "", fix_counts
    
    except Exception as e:
        return False, str(e), fix_counts

def main():
    controls_dir = Path("d:/ebs-insight/knowledge/controls")
    json_files = sorted(controls_dir.glob("*.json"))
    
    # Skip metadata.json
    json_files = [f for f in json_files if f.name != "metadata.json"]
    
    print(f"Found {len(json_files)} control files to fix\n")
    print("=" * 80)
    
    total_fixes = {
        "keywords_fixed": 0,
        "result_schema_fixed": 0,
        "intent_remapped": 0,
        "files_processed": 0,
        "files_failed": 0,
    }
    
    for file_path in json_files:
        success, error_msg, fixes = fix_control_file(file_path)
        
        if success:
            total_fixes["files_processed"] += 1
            total_fixes["keywords_fixed"] += fixes["keywords_fixed"]
            total_fixes["result_schema_fixed"] += fixes["result_schema_fixed"]
            total_fixes["intent_remapped"] += fixes["intent_remapped"]
            
            status = "✓"
            details = []
            if fixes["keywords_fixed"] > 0:
                details.append(f"keywords: 1")
            if fixes["result_schema_fixed"] > 0:
                details.append(f"schemas: 1")
            if fixes["intent_remapped"] > 0:
                details.append(f"intent: remapped")
            
            detail_str = " | ".join(details) if details else "up-to-date"
            print(f"{status} {file_path.name:40} [{detail_str}]")
        else:
            total_fixes["files_failed"] += 1
            print(f"✗ {file_path.name:40} [ERROR: {error_msg}]")
    
    print("=" * 80)
    print(f"\nSUMMARY:")
    print(f"  Files processed:         {total_fixes['files_processed']}/{len(json_files)}")
    print(f"  Files failed:            {total_fixes['files_failed']}")
    print(f"  Keywords fixed:          {total_fixes['keywords_fixed']}")
    print(f"  Result schemas fixed:    {total_fixes['result_schema_fixed']}")
    print(f"  Intent values remapped:  {total_fixes['intent_remapped']}")
    print(f"  TOTAL FIXES APPLIED:     {total_fixes['keywords_fixed'] + total_fixes['result_schema_fixed'] + total_fixes['intent_remapped']}")

if __name__ == "__main__":
    main()
