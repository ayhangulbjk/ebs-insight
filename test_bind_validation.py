"""
Quick test for bind validation improvements.
Tests type conversion, strict mode, and error cases.
"""

from src.db.executor import QueryExecutor, QueryExecutionError


def test_bind_type_conversion():
    """Test type conversion logic"""
    executor = QueryExecutor(None)  # No pool needed for this test
    
    print("✓ Testing type conversion...")
    
    # Test 1: String to int conversion
    result = executor._convert_bind_type("123", "int", "test_id")
    assert result == 123, f"Expected 123, got {result}"
    print("  ✓ String '123' → int 123")
    
    # Test 2: Invalid int conversion
    try:
        executor._convert_bind_type("not_a_number", "int", "test_id")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  ✓ Invalid int rejected: {e}")
    
    # Test 3: Bool conversion
    result = executor._convert_bind_type("true", "bool", "test_flag")
    assert result == True, f"Expected True, got {result}"
    print("  ✓ String 'true' → bool True")
    
    # Test 4: Date format validation
    result = executor._convert_bind_type("2024-01-15", "date", "test_date")
    assert result == "2024-01-15"
    print("  ✓ Date format '2024-01-15' accepted")
    
    # Test 5: Invalid date format
    try:
        executor._convert_bind_type("15/01/2024", "date", "test_date")
        assert False, "Should have raised ValueError"
    except ValueError as e:
        print(f"  ✓ Invalid date format rejected: {e}")


def test_bind_validation_strict():
    """Test strict mode: reject unexpected binds"""
    executor = QueryExecutor(None)
    
    print("\n✓ Testing strict validation...")
    
    # Schema expects only 'manager_id'
    bind_schema = [
        {"name": "manager_id", "type": "int", "optional": False}
    ]
    
    # Test 1: Valid bind
    binds = {"manager_id": "100"}
    validated = executor._validate_binds(binds, bind_schema)
    assert validated["manager_id"] == 100
    print("  ✓ Valid bind accepted and converted")
    
    # Test 2: Unexpected bind (security risk)
    binds_malicious = {"manager_id": 100, "evil_param": "DROP TABLE"}
    try:
        executor._validate_binds(binds_malicious, bind_schema)
        assert False, "Should have rejected unexpected bind"
    except QueryExecutionError as e:
        print(f"  ✓ Unexpected bind rejected: {e}")
    
    # Test 3: Missing required bind
    binds_missing = {}
    try:
        executor._validate_binds(binds_missing, bind_schema)
        assert False, "Should have rejected missing required bind"
    except QueryExecutionError as e:
        print(f"  ✓ Missing required bind rejected: {e}")
    
    # Test 4: Optional bind missing (should be OK)
    bind_schema_optional = [
        {"name": "status", "type": "str", "optional": True}
    ]
    validated = executor._validate_binds({}, bind_schema_optional)
    assert validated == {}
    print("  ✓ Missing optional bind accepted")


if __name__ == "__main__":
    print("=" * 60)
    print("BIND VALIDATION SECURITY TEST")
    print("=" * 60)
    
    try:
        test_bind_type_conversion()
        test_bind_validation_strict()
        
        print("\n" + "=" * 60)
        print("✅ ALL TESTS PASSED - Bind validation is secure!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
