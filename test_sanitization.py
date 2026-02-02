"""
Test sensitive data sanitization with defense-in-depth approach.
Validates both schema-based and pattern-based redaction.
"""

from src.db.sanitizer import Sanitizer


def test_schema_based_redaction():
    """Test redaction based on schema sensitive flag"""
    print("✓ Testing schema-based redaction...")
    
    # Schema marks 'password' as sensitive
    schema = [
        {"name": "user_id", "sensitive": False},
        {"name": "password", "sensitive": True},
        {"name": "status", "sensitive": False}
    ]
    
    rows = [
        {"user_id": 100, "password": "secret123", "status": "ACTIVE"},
        {"user_id": 101, "password": "pass456", "status": "INACTIVE"}
    ]
    
    result = Sanitizer.sanitize_result(rows, schema)
    
    # Verify password is redacted
    assert result["rows"][0]["password"] == "[REDACTED]"
    assert result["rows"][1]["password"] == "[REDACTED]"
    
    # Verify other columns are intact
    assert result["rows"][0]["user_id"] == 100
    assert result["rows"][0]["status"] == "ACTIVE"
    
    print(f"  ✓ Schema-marked sensitive field redacted: {result['redaction_count']} redactions")
    print()


def test_pattern_based_redaction():
    """Test automatic redaction based on column name patterns"""
    print("✓ Testing pattern-based redaction (defense-in-depth)...")
    
    # Schema does NOT mark any columns as sensitive
    # But column names match sensitive patterns
    schema = [
        {"name": "user_name", "sensitive": False},
        {"name": "email_address", "sensitive": False},
        {"name": "description", "sensitive": False}
    ]
    
    rows = [
        {
            "user_name": "ADMIN",  # Matches ORACLE_USERNAMES pattern
            "email_address": "admin@example.com",  # Matches EMAIL pattern
            "description": "System admin"
        }
    ]
    
    result = Sanitizer.sanitize_result(rows, schema)
    
    # Verify auto-redaction happened (defense-in-depth)
    assert result["rows"][0]["user_name"] == "[REDACTED]"
    assert result["rows"][0]["email_address"] == "[REDACTED]"
    
    # Non-sensitive column should be intact
    assert result["rows"][0]["description"] == "System admin"
    
    print(f"  ✓ Pattern-matched fields auto-redacted: {result['redaction_count']} redactions")
    print(f"  ✓ Defense-in-depth prevented data leakage!")
    print()


def test_combined_approach():
    """Test that schema + pattern work together"""
    print("✓ Testing combined schema + pattern approach...")
    
    # Schema marks 'password' as sensitive
    # 'user_name' not marked but will match pattern
    # 'public_data' should not be redacted
    schema = [
        {"name": "user_name", "sensitive": False},  # Will match pattern
        {"name": "password", "sensitive": True},     # Marked in schema
        {"name": "public_data", "sensitive": False}
    ]
    
    rows = [
        {
            "user_name": "SYSADMIN",
            "password": "secret",
            "public_data": "Some public info"
        }
    ]
    
    result = Sanitizer.sanitize_result(rows, schema)
    
    # Both should be redacted (one from schema, one from pattern)
    assert result["rows"][0]["user_name"] == "[REDACTED]"
    assert result["rows"][0]["password"] == "[REDACTED]"
    
    # Public data intact
    assert result["rows"][0]["public_data"] == "Some public info"
    
    assert result["redaction_count"] == 2
    print(f"  ✓ Combined approach: {result['redaction_count']} redactions")
    print("  ✓ Schema-marked + pattern-matched both protected")
    print()


def test_no_false_positives():
    """Test that normal columns are not redacted"""
    print("✓ Testing no false positives...")
    
    schema = [
        {"name": "manager_id", "sensitive": False},
        {"name": "status_code", "sensitive": False},
        {"name": "description", "sensitive": False}
    ]
    
    rows = [
        {
            "manager_id": 12345,
            "status_code": "ACTIVE",
            "description": "Normal description"
        }
    ]
    
    result = Sanitizer.sanitize_result(rows, schema)
    
    # None should be redacted
    assert result["rows"][0]["manager_id"] == 12345
    assert result["rows"][0]["status_code"] == "ACTIVE"
    assert result["rows"][0]["description"] == "Normal description"
    
    assert result["redaction_count"] == 0
    print("  ✓ No false positives - normal columns intact")
    print()


def test_edge_cases():
    """Test edge cases: empty rows, no schema, etc."""
    print("✓ Testing edge cases...")
    
    # Empty rows
    result = Sanitizer.sanitize_result([], [])
    assert result["rows"] == []
    assert result["redaction_count"] == 0
    print("  ✓ Empty rows handled")
    
    # Schema with no sensitive marking + no pattern match
    schema = [{"name": "id", "sensitive": False}]
    rows = [{"id": 1}]
    result = Sanitizer.sanitize_result(rows, schema)
    assert result["rows"][0]["id"] == 1
    print("  ✓ Non-sensitive data passed through")
    
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("SENSITIVE DATA SANITIZATION TEST (Defense-in-Depth)")
    print("=" * 60)
    print()
    
    try:
        test_schema_based_redaction()
        test_pattern_based_redaction()
        test_combined_approach()
        test_no_false_positives()
        test_edge_cases()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED - Defense-in-depth sanitization works!")
        print("=" * 60)
        print()
        print("Summary:")
        print("  ✓ Schema-based redaction: Working")
        print("  ✓ Pattern-based fallback: Working")
        print("  ✓ Combined approach: Working")
        print("  ✓ No false positives: Verified")
        print("  ✓ Data leakage prevention: Enhanced")
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
