"""
Shared utilities for judge runner scripts.
This module consolidates common logic used by py_runner, cpp_runner, and cs_runner.
"""

import io
from contextlib import redirect_stdout


def get_tokens(text):
    """
    Split text into tokens (whitespace-separated words).
    Used for standard output comparison.
    
    Args:
        text: String to tokenize
        
    Returns:
        List of tokens, or empty list if text is None/empty
    """
    if not text:
        return []
    return text.strip().split()


def compare_outputs(user_output, expected_output):
    """
    Compare user output with expected output using token-based comparison.
    
    Args:
        user_output: Output from user's program
        expected_output: Expected output from test case
        
    Returns:
        True if outputs match (ignoring extra whitespace), False otherwise
    """
    user_tokens = get_tokens(user_output)
    expected_tokens = get_tokens(expected_output)
    return user_tokens == expected_tokens


def check_verdict_with_checker(checker_module, test_input, user_output, expected_output):
    """
    Run custom checker to determine verdict.
    Suppresses checker's stdout to prevent JSON corruption.
    
    Args:
        checker_module: Imported checker module with check() function
        test_input: Input data for the test
        user_output: Output from user's program
        expected_output: Expected output from test case
        
    Returns:
        Tuple of (verdict, error_message)
        - verdict: "Accepted", "Wrong Answer", or "Judge Error"
        - error_message: Error details if judge error occurred, empty string otherwise
    """
    try:
        # Suppress checker's stdout to prevent JSON corruption
        f_dummy = io.StringIO()
        with redirect_stdout(f_dummy):
            is_ok = checker_module.check(test_input, user_output, expected_output)
        
        verdict = "Accepted" if is_ok else "Wrong Answer"
        return verdict, ""
    except Exception as check_err:
        return "Judge Error", f"\nChecker failed: {check_err}"


def determine_verdict(return_code, user_output, expected_output, test_input="", checker_module=None):
    """
    Determine verdict based on return code and output comparison.
    
    Args:
        return_code: Process return code (124 = timeout, != 0 = runtime error)
        user_output: Output from user's program
        expected_output: Expected output from test case
        test_input: Input data for the test (required for custom checkers)
        checker_module: Optional custom checker module
        
    Returns:
        Tuple of (verdict, error_message)
    """
    if return_code == 124:  # Linux timeout signal
        return "Time Limit Exceeded", ""
    elif return_code != 0:
        return "Runtime Error", ""
    else:
        # Check output correctness
        if checker_module:
            return check_verdict_with_checker(
                checker_module, test_input, user_output, expected_output
            )
        else:
            if compare_outputs(user_output, expected_output):
                return "Accepted", ""
            else:
                return "Wrong Answer", ""
