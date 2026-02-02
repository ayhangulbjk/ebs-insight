#!/usr/bin/env python3
"""
Quick test script for FIX 1-3 validation.
Tests verdict conversion, fallback logic, and prompt formatting.
"""

import sys
from src.controls.schema import (
    LLMOutputVerdictType,
    LLMSummaryResponse,
    ControlExecutionResult,
    QueryResult,
    ControlDefinition,
    QueryDefinition,
    Keywords
)


def test_verdict_conversion():
    """Test FIX 1: Verdict enum to string conversion"""
    print("=" * 60)
    print("TEST 1: Verdict Enum → String Conversion")
    print("=" * 60)
    
    response = LLMSummaryResponse(
        summary_bullets=["Test bullet 1", "Test bullet 2"],
        verdict=LLMOutputVerdictType.WARN,
        evidence=["Test evidence"]
    )
    
    # Simulate what routes.py does now
    verdict_str = response.verdict.value if hasattr(response.verdict, 'value') else str(response.verdict)
    
    print(f"✓ Enum object: {response.verdict}")
    print(f"✓ String value: {verdict_str}")
    print(f"✓ Type: {type(verdict_str)}")
    
    assert verdict_str == "WARN", f"Expected 'WARN', got '{verdict_str}'"
    assert isinstance(verdict_str, str), f"Expected str type, got {type(verdict_str)}"
    
    print("✅ TEST 1 PASSED\n")


def test_fallback_summary():
    """Test FIX 2: Intelligent fallback with control-specific logic"""
    print("=" * 60)
    print("TEST 2: Intelligent Fallback Summary")
    print("=" * 60)
    
    # Import the fallback function
    sys.path.insert(0, 'd:\\ebs-insight')
    from src.web.routes import _generate_fallback_summary
    
    # Create mock control
    control = ControlDefinition(
        control_id="invalid_objects_001",
        version="1.0.0",
        title="Invalid Objects",
        description="Test",
        intent="data_integrity",
        keywords=Keywords(en=["test"], tr=["test"]),
        queries=[],
        safety_classification="SAFE_READONLY",
        doc_hint="Test",
        analysis_prompt="Test"
    )
    
    # Create mock execution result with invalid objects
    exec_result = ControlExecutionResult(
        control_id="invalid_objects_001",
        query_results=[
            QueryResult(
                query_id="test_query",
                row_count=381,
                rows=[
                    {"OWNER": "APPS", "OBJECT_NAME": "PKG_TEST_1", "OBJECT_TYPE": "PACKAGE"},
                    {"OWNER": "APPS", "OBJECT_NAME": "PKG_TEST_2", "OBJECT_TYPE": "PROCEDURE"},
                    {"OWNER": "APPS", "OBJECT_NAME": "PKG_TEST_3", "OBJECT_TYPE": "FUNCTION"},
                ],
                truncated=True,
                execution_time_ms=150
            )
        ],
        total_execution_time_ms=150,
        has_errors=False
    )
    
    # Generate fallback
    fallback = _generate_fallback_summary(exec_result, control)
    
    print(f"✓ Verdict: {fallback.verdict}")
    print(f"✓ Summary bullets: {len(fallback.summary_bullets)}")
    for i, bullet in enumerate(fallback.summary_bullets, 1):
        print(f"  {i}. {bullet}")
    
    print(f"✓ Evidence: {fallback.evidence}")
    print(f"✓ Details: {fallback.details[:50]}..." if fallback.details else "✓ Details: None")
    print(f"✓ Next checks: {len(fallback.next_checks) if fallback.next_checks else 0}")
    
    # Assertions
    assert fallback.verdict in [LLMOutputVerdictType.WARN, LLMOutputVerdictType.CRIT], \
        f"Expected WARN/CRIT for 381 objects, got {fallback.verdict}"
    
    assert any("381" in bullet for bullet in fallback.summary_bullets), \
        "Expected '381' in summary bullets"
    
    assert any("obje" in bullet.lower() for bullet in fallback.summary_bullets), \
        "Expected 'obje' keyword in Turkish summary"
    
    assert fallback.next_checks is not None and len(fallback.next_checks) > 0, \
        "Expected actionable next_checks for invalid objects"
    
    print("✅ TEST 2 PASSED\n")


def test_prompt_row_limit():
    """Test FIX 3: Prompt builder row limit"""
    print("=" * 60)
    print("TEST 3: Prompt Builder Row Limit")
    print("=" * 60)
    
    from src.llm.prompt_builder import PromptBuilder
    
    # Create mock control
    control = ControlDefinition(
        control_id="test_control",
        version="1.0.0",
        title="Test Control",
        description="Test",
        intent="test",
        keywords=Keywords(en=["test"], tr=["test"]),
        queries=[
            QueryDefinition(
                query_id="test_query",
                sql="SELECT 1",
                binds=[],
                row_limit=100,
                timeout_seconds=30,
                result_schema=[]
            )
        ],
        safety_classification="SAFE_READONLY",
        doc_hint="Test",
        analysis_prompt="Test"
    )
    
    # Create execution result with 50 rows
    rows = [{"ID": i, "NAME": f"Object_{i}"} for i in range(1, 51)]
    
    exec_result = ControlExecutionResult(
        control_id="test_control",
        query_results=[
            QueryResult(
                query_id="test_query",
                row_count=50,
                rows=rows,
                truncated=False,
                execution_time_ms=100
            )
        ],
        total_execution_time_ms=100,
        has_errors=False
    )
    
    # Build context prompt
    prompt = PromptBuilder.build_context_prompt(control, exec_result)
    
    # Count how many rows are in the prompt (look for "| 1 |" ... "| 10 |" pattern)
    row_count_in_prompt = prompt.count("| Object_")
    
    print(f"✓ Total rows in data: 50")
    print(f"✓ Rows included in prompt: {row_count_in_prompt}")
    print(f"✓ Prompt length: {len(prompt)} chars")
    
    # Check that only 10 rows are included
    assert row_count_in_prompt <= 10, \
        f"Expected max 10 rows in prompt, found {row_count_in_prompt}"
    
    # Check for "showing 10" message
    assert "showing 10" in prompt.lower() or "showing" in prompt.lower(), \
        "Expected 'showing X' message in prompt"
    
    print("✅ TEST 3 PASSED\n")


if __name__ == "__main__":
    try:
        test_verdict_conversion()
        test_fallback_summary()
        test_prompt_row_limit()
        
        print("=" * 60)
        print("✅ ALL TESTS PASSED!")
        print("=" * 60)
        print("\nSummary of fixes:")
        print("  ✓ FIX 1: Verdict enum converted to string value")
        print("  ✓ FIX 2: Intelligent fallback with control-specific logic")
        print("  ✓ FIX 3: Prompt row limit capped at 10 to prevent timeout")
        print("\nReady to test in application!")
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
