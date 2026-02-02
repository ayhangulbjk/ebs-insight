"""
Test log sanitization to prevent log injection attacks.
Validates that user input is safely logged without control characters or newlines.
"""

from src.observability.log_sanitizer import LogSanitizer, safe_log_value, safe_log_dict


def test_newline_sanitization():
    """Test that newlines are escaped"""
    print("✓ Testing newline sanitization...")
    
    # Malicious input with newlines
    malicious = "Normal text\nFAKE LOG ENTRY: ERROR occurred"
    sanitized = LogSanitizer.sanitize(malicious)
    
    # Newlines should be escaped
    assert "\n" not in sanitized
    assert "\\n" in sanitized
    print(f"  ✓ Input: '{malicious[:30]}...'")
    print(f"  ✓ Sanitized: '{sanitized[:50]}...'")
    print()


def test_control_char_removal():
    """Test that control characters are removed"""
    print("✓ Testing control character removal...")
    
    # Input with control chars
    dirty = "test\x00data\x01with\x1fcontrol\x7fchars"
    sanitized = LogSanitizer.sanitize(dirty)
    
    # Control chars should be removed
    assert "\x00" not in sanitized
    assert "\x01" not in sanitized
    assert "\x1f" not in sanitized
    assert "\x7f" not in sanitized
    assert "test" in sanitized and "data" in sanitized
    
    print(f"  ✓ Control characters removed: '{dirty}' → '{sanitized}'")
    print()


def test_length_truncation():
    """Test that long strings are truncated"""
    print("✓ Testing length truncation...")
    
    # Very long string
    long_str = "A" * 500
    sanitized = LogSanitizer.sanitize(long_str, max_length=100)
    
    # Should be truncated
    assert len(sanitized) <= 103  # 100 + '...'
    assert sanitized.endswith("...")
    
    print(f"  ✓ Long string truncated: {len(long_str)} chars → {len(sanitized)} chars")
    print()


def test_tab_sanitization():
    """Test that tabs are escaped"""
    print("✓ Testing tab sanitization...")
    
    malicious = "column1\tcolumn2\tcolumn3"
    sanitized = LogSanitizer.sanitize(malicious)
    
    # Tabs should be escaped
    assert "\t" not in sanitized
    assert "\\t" in sanitized
    
    print(f"  ✓ Tabs escaped: '{malicious}' → '{sanitized}'")
    print()


def test_log_injection_prevention():
    """Test prevention of actual log injection attacks"""
    print("✓ Testing log injection attack prevention...")
    
    # Real-world log injection attempts
    attacks = [
        "user input\n[2024-01-01 00:00:00] ERROR: Fake error injected",
        "normal\r\nINFO: Injected log line",
        "test\n\n\n[CRITICAL] System compromised",
    ]
    
    for attack in attacks:
        sanitized = LogSanitizer.sanitize(attack)
        
        # No actual newlines should remain
        assert "\n" not in sanitized, f"Newline found in: {sanitized}"
        assert "\r" not in sanitized, f"Carriage return found in: {sanitized}"
        
        print(f"  ✓ Attack blocked: '{attack[:40]}...'")
    
    print()


def test_dict_sanitization():
    """Test dictionary sanitization"""
    print("✓ Testing dictionary sanitization...")
    
    dirty_dict = {
        "user_input": "test\ninjection",
        "status": "OK",
        "data": "value\twith\ttabs"
    }
    
    sanitized = LogSanitizer.sanitize_dict(dirty_dict)
    
    # All values should be sanitized
    assert "\\n" in sanitized["user_input"]
    assert "\n" not in sanitized["user_input"]
    assert "\\t" in sanitized["data"]
    assert "\t" not in sanitized["data"]
    assert sanitized["status"] == "OK"  # Normal values unchanged
    
    print(f"  ✓ Dictionary sanitized:")
    print(f"    Before: {dirty_dict}")
    print(f"    After: {sanitized}")
    print()


def test_list_sanitization():
    """Test list sanitization"""
    print("✓ Testing list sanitization...")
    
    dirty_list = ["normal", "with\nnewline", "with\x00null"]
    sanitized = LogSanitizer.sanitize_list(dirty_list)
    
    assert sanitized[0] == "normal"
    assert "\\n" in sanitized[1]
    assert "\n" not in sanitized[1]
    assert "\x00" not in sanitized[2]
    
    print(f"  ✓ List sanitized: {dirty_list} → {sanitized}")
    print()


def test_convenience_functions():
    """Test convenience wrapper functions"""
    print("✓ Testing convenience functions...")
    
    # Test safe_log_value
    unsafe = "test\nvalue"
    safe = safe_log_value(unsafe)
    assert "\n" not in safe
    assert "\\n" in safe
    print(f"  ✓ safe_log_value: '{unsafe}' → '{safe}'")
    
    # Test safe_log_dict
    unsafe_dict = {"key": "val\nue"}
    safe_dict = safe_log_dict(unsafe_dict)
    assert "\n" not in safe_dict["key"]
    print(f"  ✓ safe_log_dict: {unsafe_dict} → {safe_dict}")
    
    print()


def test_none_handling():
    """Test handling of None values"""
    print("✓ Testing None value handling...")
    
    result = LogSanitizer.sanitize(None)
    assert result == "None"
    
    result = safe_log_value(None)
    assert result == "None"
    
    print("  ✓ None values handled correctly")
    print()


def test_special_characters():
    """Test handling of special but safe characters"""
    print("✓ Testing special character handling...")
    
    # Unicode, symbols, etc should be preserved
    special = "Türkçe: ğüşıöç, Symbols: !@#$%^&*()"
    sanitized = LogSanitizer.sanitize(special)
    
    # Should preserve these
    assert "ğ" in sanitized
    assert "ü" in sanitized
    assert "!" in sanitized
    assert "@" in sanitized
    
    print(f"  ✓ Special characters preserved: '{special}'")
    print()


def test_real_world_scenario():
    """Test realistic logging scenario"""
    print("✓ Testing real-world logging scenario...")
    
    # Simulate user input with potential injection
    user_prompt = "Show me status\n[CRITICAL] Fake alert\r\nDROP TABLE users"
    query_id = "test_query\x00\x01"
    
    # What would be logged
    safe_prompt = safe_log_value(user_prompt, max_length=50)
    safe_qid = safe_log_value(query_id)
    
    log_message = f"[{safe_qid}] Executing: {safe_prompt}"
    
    # Verify no injection possible
    assert "\n" not in log_message
    assert "\r" not in log_message
    assert "\x00" not in log_message
    
    print(f"  ✓ Safe log message: '{log_message}'")
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("LOG SANITIZATION TEST")
    print("=" * 60)
    print()
    
    try:
        test_newline_sanitization()
        test_control_char_removal()
        test_length_truncation()
        test_tab_sanitization()
        test_log_injection_prevention()
        test_dict_sanitization()
        test_list_sanitization()
        test_convenience_functions()
        test_none_handling()
        test_special_characters()
        test_real_world_scenario()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED - Log sanitization is working!")
        print("=" * 60)
        print()
        print("Summary:")
        print("  ✓ Newline injection prevented")
        print("  ✓ Control characters removed")
        print("  ✓ Length truncation working")
        print("  ✓ Tab escaping working")
        print("  ✓ Log injection attacks blocked")
        print("  ✓ Dict/List sanitization working")
        print("  ✓ Special characters preserved")
        print("  ✓ Real-world scenarios protected")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
