#!/usr/bin/env python3
"""
Test script to verify transport layer fixes are working correctly.
"""

import asyncio
import json
from types import SimpleNamespace
from core.transport_layer import extract_json_from_text, universal_send

def test_extract_json_from_text():
    """Test the JSON extraction function with various inputs."""
    print("Testing extract_json_from_text function...")
    
    # Test 1: Valid JSON with ChatGPT prefix
    test_text1 = 'json\nCopy\nEdit\n{"interface": "telegram_bot", "action": "send_message", "payload": {"text": "Hello"}}'
    result1 = extract_json_from_text(test_text1)
    print(f"Test 1 - ChatGPT prefix: {result1}")
    
    # Test 2: System message (should return None)
    test_text2 = '[ERROR] This is a system error message'
    result2 = extract_json_from_text(test_text2)
    print(f"Test 2 - System message: {result2}")
    
    # Test 3: Error report (should return None)
    test_text3 = '{"error_report": "Failed to process action", "details": "Interface not found"}'
    result3 = extract_json_from_text(test_text3)
    print(f"Test 3 - Error report: {result3}")
    
    # Test 4: Valid JSON array
    test_text4 = '[{"interface": "telegram_bot", "action": "send_message", "payload": {"text": "Test 1"}}, {"interface": "telegram_bot", "action": "send_message", "payload": {"text": "Test 2"}}]'
    result4 = extract_json_from_text(test_text4)
    print(f"Test 4 - JSON array: {result4}")
    
    # Test 5: Plain text (should return None)
    test_text5 = 'This is just a normal text message without any JSON'
    result5 = extract_json_from_text(test_text5)
    print(f"Test 5 - Plain text: {result5}")
    
    # Test 6: Malformed JSON (should return None)
    test_text6 = '{"interface": "telegram_bot", "action": "send_message", "payload": {"text": "Missing closing brace"'
    result6 = extract_json_from_text(test_text6)
    print(f"Test 6 - Malformed JSON: {result6}")
    
    print("\nJSON extraction tests completed!")

def test_system_message_detection():
    """Test that system messages are properly detected and skipped."""
    print("\nTesting system message detection...")
    
    system_messages = [
        '[ERROR] Database connection failed',
        '[WARNING] Rate limit approaching',
        '[INFO] Plugin loaded successfully',
        '[DEBUG] Processing message: Hello world',
        '{"error_report": "Action failed", "reason": "Invalid interface"}',
        '{"correction_needed": true, "message": "Please fix the action"}'
    ]
    
    for msg in system_messages:
        result = extract_json_from_text(msg)
        status = "✓ SKIPPED" if result is None else "✗ PROCESSED"
        print(f"{status}: {msg[:50]}...")
    
    print("System message detection tests completed!")

async def test_error_reporting():
    """Test the error reporting system."""
    print("\nTesting error reporting system...")
    
    # Create a mock interface send function
    async def mock_send_function(*args, text: str = None, **kwargs):
        print(f"Mock send called with text: {text[:100]}...")
        return True
    
    # Test with normal text
    await universal_send(mock_send_function, text="This is normal text")
    
    # Test with system error (should not be parsed as JSON)
    await universal_send(mock_send_function, text="[ERROR] System failure detected")
    
    # Test with error report (should not be parsed as JSON)
    await universal_send(mock_send_function, text='{"error_report": "Action parsing failed", "details": "Invalid JSON syntax"}')
    
    print("Error reporting tests completed!")

if __name__ == "__main__":
    # Run synchronous tests
    test_extract_json_from_text()
    test_system_message_detection()
    
    # Run async tests
    asyncio.run(test_error_reporting())
    
    print("\n✅ All transport layer tests completed!")
