# -*- coding: utf-8 -*-

"""
Common utilities for OpenCTP SDK
"""

import logging
import os
import sys
from typing import Dict, Any, Optional
from pathlib import Path
import json

def setup_logger(name: str, level: int = logging.INFO, log_file: Optional[str] = None) -> logging.Logger:
    """
    Setup logger for OpenCTP SDK
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional log file path
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Remove existing handlers to avoid duplication
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger

def load_config(config_path: str) -> Dict[str, Any]:
    """
    Load configuration from JSON file
    
    Args:
        config_path: Path to configuration file
        
    Returns:
        Configuration dictionary
        
    Raises:
        FileNotFoundError: If config file not found
        json.JSONDecodeError: If config file is invalid JSON
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Configuration file not found: {config_path}")
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    return config

def save_config(config: Dict[str, Any], config_path: str) -> None:
    """
    Save configuration to JSON file
    
    Args:
        config: Configuration dictionary
        config_path: Path to save configuration file
    """
    # Create directory if it doesn't exist
    Path(config_path).parent.mkdir(parents=True, exist_ok=True)
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def find_ctp_library_path(version: str = "6.7.2_20230913") -> str:
    """
    Find the appropriate CTP library path for current platform
    
    Args:
        version: CTP version to use
        
    Returns:
        Path to CTP library directory
        
    Raises:
        FileNotFoundError: If library path not found
    """
    current_dir = Path(__file__).parent.parent.parent
    
    # Determine platform
    if sys.platform.startswith('win'):
        if sys.maxsize > 2**32:
            platform = "win64"
        else:
            platform = "win32"
    elif sys.platform.startswith('linux'):
        platform = "linux64"
    elif sys.platform.startswith('darwin'):
        platform = "mac64"
    else:
        raise RuntimeError(f"Unsupported platform: {sys.platform}")
    
    # Construct library path
    lib_path = current_dir / version / platform
    
    if not lib_path.exists():
        raise FileNotFoundError(f"CTP library not found at: {lib_path}")
    
    return str(lib_path)

def add_ctp_library_path(version: str = "6.7.2_20230913") -> None:
    """
    Add CTP library path to Python path
    
    Args:
        version: CTP version to use
    """
    lib_path = find_ctp_library_path(version)
    if lib_path not in sys.path:
        sys.path.insert(0, lib_path)

def validate_instrument_id(instrument_id: str) -> bool:
    """
    Validate instrument ID format
    
    Args:
        instrument_id: Instrument ID to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not instrument_id or not isinstance(instrument_id, str):
        return False
    
    # Basic validation - should be non-empty and alphanumeric
    return instrument_id.isalnum() and len(instrument_id) <= 30

def format_price(price: float, precision: int = 2) -> str:
    """
    Format price with specified precision
    
    Args:
        price: Price value
        precision: Decimal precision
        
    Returns:
        Formatted price string
    """
    return f"{price:.{precision}f}"

def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Float value or default
    """
    try:
        return float(value)
    except (ValueError, TypeError):
        return default

def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        Int value or default
    """
    try:
        return int(value)
    except (ValueError, TypeError):
        return default

def safe_str(value: Any, default: str = "") -> str:
    """
    Safely convert value to string
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
        
    Returns:
        String value or default
    """
    try:
        if value is None:
            return default
        return str(value).strip()
    except:
        return default