"""
Test SQL timeout enforcement.
Validates that queries exceeding timeout are cancelled.
"""

import time
import threading
from unittest.mock import Mock, MagicMock
from src.db.executor import QueryExecutor


def test_timeout_enforcement():
    """Test that timeout is enforced on slow queries"""
    print("✓ Testing SQL timeout enforcement...")
    
    # Create mock pool and cursor
    mock_pool = Mock()
    mock_conn = Mock()
    mock_cursor = Mock()
    
    mock_pool.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate a slow query (takes 5 seconds)
    def slow_execute(*args, **kwargs):
        time.sleep(5)
    
    mock_cursor.execute = slow_execute
    
    executor = QueryExecutor(mock_pool)
    
    # Test 1: Query that times out (timeout=1s, query takes 5s)
    print("  Testing timeout (1s timeout, 5s query)...")
    try:
        start = time.time()
        executor._execute_with_timeout(mock_cursor, "SELECT 1", None, timeout_seconds=1)
        assert False, "Should have raised TimeoutError"
    except TimeoutError as e:
        elapsed = time.time() - start
        print(f"  ✓ Query timed out after {elapsed:.2f}s (expected ~1s): {e}")
        assert elapsed < 2, f"Timeout took too long: {elapsed}s"
    
    print()


def test_fast_query_no_timeout():
    """Test that fast queries complete normally"""
    print("✓ Testing fast query (no timeout)...")
    
    # Create mock pool and cursor
    mock_pool = Mock()
    mock_conn = Mock()
    mock_cursor = Mock()
    
    mock_pool.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate a fast query (instant)
    mock_cursor.execute = Mock()
    
    executor = QueryExecutor(mock_pool)
    
    # Test: Fast query completes within timeout
    start = time.time()
    executor._execute_with_timeout(mock_cursor, "SELECT 1", None, timeout_seconds=5)
    elapsed = time.time() - start
    
    print(f"  ✓ Query completed in {elapsed:.2f}s (well under 5s timeout)")
    assert elapsed < 1, "Should complete almost instantly"
    assert mock_cursor.execute.called, "execute should have been called"
    print()


def test_query_exception_propagation():
    """Test that database errors are propagated correctly"""
    print("✓ Testing exception propagation...")
    
    # Create mock pool and cursor
    mock_pool = Mock()
    mock_conn = Mock()
    mock_cursor = Mock()
    
    mock_pool.get_connection.return_value = mock_conn
    mock_conn.cursor.return_value = mock_cursor
    
    # Simulate query that raises error
    mock_cursor.execute.side_effect = Exception("Simulated DB error")
    
    executor = QueryExecutor(mock_pool)
    
    # Test: Exception is propagated
    try:
        executor._execute_with_timeout(mock_cursor, "SELECT 1", None, timeout_seconds=5)
        assert False, "Should have raised Exception"
    except Exception as e:
        print(f"  ✓ Exception propagated correctly: {e}")
        assert "Simulated DB error" in str(e)
    
    print()


if __name__ == "__main__":
    print("=" * 60)
    print("SQL TIMEOUT ENFORCEMENT TEST")
    print("=" * 60)
    print()
    
    try:
        test_fast_query_no_timeout()
        test_query_exception_propagation()
        test_timeout_enforcement()  # This one is slow (5s), run last
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED - Timeout enforcement is working!")
        print("=" * 60)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
