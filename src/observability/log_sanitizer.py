"""
Log Sanitization Utilities.
Per SECURITY.MD § 4.3 (Logging Policy).

Prevents log injection attacks by sanitizing user input before logging.
"""

import re
from typing import Any


class LogSanitizer:
    """
    Sanitize values before logging to prevent log injection.
    
    Log injection risks:
    - Newline injection (split log entries)
    - Control character injection
    - Log forging (fake log entries)
    """
    
    # Control characters to remove (except space and tab)
    CONTROL_CHARS = r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'
    
    # Max length for logged user input (prevent log flooding)
    MAX_LOG_LENGTH = 200
    
    @classmethod
    def sanitize(cls, value: Any, max_length: int = None) -> str:
        """
        Sanitize a value for safe logging.
        
        Args:
            value: Value to sanitize (will be converted to string)
            max_length: Max length (default: MAX_LOG_LENGTH)
            
        Returns:
            Sanitized string safe for logging
        """
        if value is None:
            return "None"
        
        # Convert to string
        s = str(value)
        
        # Step 1: Remove control characters
        s = re.sub(cls.CONTROL_CHARS, '', s)
        
        # Step 2: Replace newlines with literal \n
        s = s.replace('\n', '\\n').replace('\r', '\\r')
        
        # Step 3: Replace tabs with literal \t
        s = s.replace('\t', '\\t')
        
        # Step 4: Truncate if too long
        max_len = max_length or cls.MAX_LOG_LENGTH
        if len(s) > max_len:
            s = s[:max_len] + '...'
        
        return s
    
    @classmethod
    def sanitize_dict(cls, d: dict, max_length: int = None) -> dict:
        """
        Sanitize all values in a dictionary.
        
        Args:
            d: Dictionary to sanitize
            max_length: Max length per value
            
        Returns:
            New dictionary with sanitized values
        """
        return {
            k: cls.sanitize(v, max_length)
            for k, v in d.items()
        }
    
    @classmethod
    def sanitize_list(cls, lst: list, max_length: int = None) -> list:
        """
        Sanitize all items in a list.
        
        Args:
            lst: List to sanitize
            max_length: Max length per item
            
        Returns:
            New list with sanitized items
        """
        return [cls.sanitize(item, max_length) for item in lst]


def safe_log_value(value: Any, max_length: int = None) -> str:
    """
    Convenience function for sanitizing a single value for logging.
    
    Usage:
        logger.info(f"User input: {safe_log_value(user_prompt)}")
    
    Args:
        value: Value to sanitize
        max_length: Max length (default: 200)
        
    Returns:
        Sanitized string
    """
    return LogSanitizer.sanitize(value, max_length)


def safe_log_dict(d: dict, max_length: int = None) -> dict:
    """
    Convenience function for sanitizing a dictionary for logging.
    
    Usage:
        logger.info(f"Request data: {safe_log_dict(request_data)}")
    
    Args:
        d: Dictionary to sanitize
        max_length: Max length per value
        
    Returns:
        Sanitized dictionary
    """
    return LogSanitizer.sanitize_dict(d, max_length)
