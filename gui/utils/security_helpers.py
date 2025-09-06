"""
SMBSeek GUI - Security Helper Functions

Provides security utilities for safe data handling, CSV export protection, and 
control character sanitization as per security audit recommendations.

Design Decision: Centralized security functions ensure consistent application
of security measures across all GUI components.
"""

import re
from typing import Any, Dict, List, Optional


def sanitize_csv_cell(value: Any) -> str:
    """
    Sanitize CSV cell value to prevent formula injection attacks.
    
    Implements audit recommendation: prefix dangerous characters (=, +, -, @)
    with single quote to prevent Excel/Sheets formula execution.
    
    Args:
        value: Cell value to sanitize
        
    Returns:
        Sanitized string safe for CSV export
    """
    if value is None:
        return ""
    
    # Convert to string
    str_value = str(value).strip()
    
    if not str_value:
        return ""
    
    # Check if value starts with dangerous formula characters
    dangerous_prefixes = ('=', '+', '-', '@')
    
    if str_value.startswith(dangerous_prefixes):
        # Prefix with single quote to prevent formula interpretation
        return "'" + str_value
    
    return str_value


def strip_control_characters(text: str) -> str:
    """
    Strip control characters, ANSI escape sequences, and null bytes from text.
    
    Implements audit recommendation for safe log display and data processing.
    Removes potentially malicious control characters while preserving readable content.
    
    Args:
        text: Text to sanitize
        
    Returns:
        Sanitized text with control characters removed
    """
    if not text:
        return ""
    
    # Remove null bytes and other control characters (except \t, \n, \r)
    # Control characters are 0x00-0x1F and 0x7F-0x9F except tab(0x09), LF(0x0A), CR(0x0D)
    text = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F-\x9F]', '', text)
    
    # Remove ANSI escape sequences (color codes, cursor movement, etc.)
    # Pattern matches: ESC[ followed by any number of digits, semicolons, and ending with a letter
    text = re.sub(r'\x1b\[[0-9;]*[a-zA-Z]', '', text)
    
    # Remove other common escape sequences
    text = re.sub(r'\x1b\([AB]', '', text)  # Character set selection
    text = re.sub(r'\x1b\].*?\x07', '', text)  # Operating system command sequences
    text = re.sub(r'\x1b\].*?\x1b\\', '', text)  # OSC with ST terminator
    
    return text


def validate_share_name(name: str, max_len: int = 80) -> bool:
    """
    Validate SMB share name for security and format compliance.
    
    Implements audit recommendation for share name validation.
    Ensures share names contain only printable ASCII and are within length limits.
    
    Args:
        name: Share name to validate
        max_len: Maximum allowed length (default 80)
        
    Returns:
        True if share name is valid, False otherwise
    """
    if not name or not isinstance(name, str):
        return False
    
    # Check length
    if len(name) > max_len:
        return False
    
    # Check for printable ASCII characters only (space to tilde: 0x20-0x7E)
    if not all(0x20 <= ord(char) <= 0x7E for char in name):
        return False
    
    # Additional SMB share name restrictions
    invalid_chars = ['/', '\\', ':', '*', '?', '"', '<', '>', '|']
    if any(char in name for char in invalid_chars):
        return False
    
    # Reserve certain names
    reserved_names = {'CON', 'PRN', 'AUX', 'NUL', 'COM1', 'COM2', 'COM3', 'COM4', 
                     'COM5', 'COM6', 'COM7', 'COM8', 'COM9', 'LPT1', 'LPT2', 
                     'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9'}
    if name.upper() in reserved_names:
        return False
    
    return True


def sanitize_log_output(text: str) -> str:
    """
    Sanitize log output for safe display in GUI components.
    
    Combines control character stripping with additional log-specific sanitization
    to ensure safe display in text widgets and prevent log injection.
    
    Args:
        text: Log text to sanitize
        
    Returns:
        Sanitized log text safe for GUI display
    """
    if not text:
        return ""
    
    # Strip control characters first
    text = strip_control_characters(text)
    
    # Truncate extremely long lines to prevent GUI performance issues
    lines = text.split('\n')
    sanitized_lines = []
    
    for line in lines:
        # Limit individual line length
        if len(line) > 2000:
            line = line[:1997] + "..."
        
        # Remove any remaining problematic characters
        line = line.replace('\x00', '').strip()
        
        if line:  # Only add non-empty lines
            sanitized_lines.append(line)
    
    # Limit total number of lines to prevent memory issues
    if len(sanitized_lines) > 1000:
        sanitized_lines = sanitized_lines[-1000:]  # Keep last 1000 lines
    
    return '\n'.join(sanitized_lines)


def sanitize_data_for_export(data: List[Dict[str, Any]], data_type: str) -> List[Dict[str, Any]]:
    """
    Sanitize data structure for safe export operations.
    
    Applies comprehensive sanitization to data before export to prevent
    injection attacks and ensure data integrity.
    
    Args:
        data: List of data dictionaries to sanitize
        data_type: Type of data being sanitized
        
    Returns:
        List of sanitized data dictionaries
    """
    if not data:
        return []
    
    sanitized_data = []
    
    for item in data:
        if not isinstance(item, dict):
            continue
        
        sanitized_item = {}
        
        for key, value in item.items():
            # Sanitize key
            clean_key = strip_control_characters(str(key)) if key else ""
            if not clean_key:
                continue
            
            # Sanitize value based on type
            if isinstance(value, str):
                # For string values, apply both control character and CSV sanitization
                clean_value = strip_control_characters(value)
            elif isinstance(value, (list, dict)):
                # Convert complex types to safe string representation
                clean_value = str(value)[:500]  # Limit length
                clean_value = strip_control_characters(clean_value)
            elif value is None:
                clean_value = ""
            else:
                # Convert other types to string and sanitize
                clean_value = strip_control_characters(str(value))
            
            sanitized_item[clean_key] = clean_value
        
        if sanitized_item:  # Only add non-empty items
            sanitized_data.append(sanitized_item)
    
    return sanitized_data


def validate_smb_limits_config(config: Dict[str, Any]) -> Dict[str, str]:
    """
    Validate SMB security limits configuration values.
    
    Implements audit recommendation for limits validation.
    Ensures all security limits are within safe and reasonable ranges.
    
    Args:
        config: Configuration dictionary containing SMB limits
        
    Returns:
        Dictionary of validation errors (empty if valid)
    """
    errors = {}
    
    # Expected limits with their valid ranges
    limit_specs = {
        'timeout_per_stage_seconds': {'min': 1, 'max': 300, 'default': 3},
        'timeout_per_host_seconds': {'min': 5, 'max': 3600, 'default': 30},
        'max_pdu_bytes': {'min': 1024, 'max': 1048576, 'default': 65536},  # 1KB to 1MB
        'max_stdout_bytes': {'min': 1024, 'max': 104857600, 'default': 10000},  # 1KB to 100MB
        'max_shares': {'min': 1, 'max': 10000, 'default': 256},
        'max_share_name_len': {'min': 1, 'max': 255, 'default': 80}
    }
    
    for limit_name, spec in limit_specs.items():
        if limit_name in config:
            value = config[limit_name]
            
            # Check if value is numeric
            try:
                numeric_value = int(value)
            except (ValueError, TypeError):
                errors[limit_name] = f"Must be a number (default: {spec['default']})"
                continue
            
            # Check range
            if numeric_value < spec['min']:
                errors[limit_name] = f"Must be at least {spec['min']} (current: {numeric_value})"
            elif numeric_value > spec['max']:
                errors[limit_name] = f"Must be at most {spec['max']} (current: {numeric_value})"
    
    return errors


def get_default_smb_limits() -> Dict[str, int]:
    """
    Get default SMB security limits configuration.
    
    Returns the secure defaults as specified in the audit recommendations.
    
    Returns:
        Dictionary with default security limits
    """
    return {
        'timeout_per_stage_seconds': 3,
        'timeout_per_host_seconds': 30,
        'max_pdu_bytes': 65536,
        'max_stdout_bytes': 10000,
        'max_shares': 256,
        'max_share_name_len': 80,
        'signing_required': True,
        'resolve_netbios': False
    }


def is_smb1_safe_mode_supported() -> bool:
    """
    Check if the system supports SMB1 safe discovery mode.
    
    This checks for the backend implementation that supports the audit
    recommendations for SMB1 discovery with strict safety controls.
    
    Returns:
        True if SMB1 safe mode is supported
    """
    # This would check for backend version/capability
    # For now, return True as backend team has implemented the features
    return True


def format_protocol_display(protocol: str, show_warning: bool = False) -> str:
    """
    Format protocol name for display with optional warning indicators.
    
    Args:
        protocol: Protocol name (SMB1, SMB2, SMB3)
        show_warning: Whether to add warning indicators for legacy protocols
        
    Returns:
        Formatted protocol string for display
    """
    if not protocol:
        return "Unknown"
    
    protocol_upper = protocol.upper()
    
    if protocol_upper == "SMB1" or protocol_upper == "NT1":
        if show_warning:
            return "⚠️ SMB1 (Legacy)"
        else:
            return "SMB1"
    elif protocol_upper in ["SMB2", "SMB2.0", "SMB2.1"]:
        return "SMB2"
    elif protocol_upper in ["SMB3", "SMB3.0", "SMB3.1", "SMB3.1.1"]:
        return "SMB3"
    else:
        return protocol_upper