# -*- coding: utf-8 -*-

"""
Custom exceptions for OpenCTP SDK
"""

class OpenCTPError(Exception):
    """Base exception for OpenCTP SDK"""
    def __init__(self, message: str, error_code: int = 0):
        super().__init__(message)
        self.error_code = error_code
        self.message = message

class ConnectionError(OpenCTPError):
    """Raised when connection to CTP server fails"""
    pass

class AuthenticationError(OpenCTPError):
    """Raised when authentication fails"""
    pass

class TradingError(OpenCTPError):
    """Raised when trading operations fail"""
    pass

class MarketDataError(OpenCTPError):
    """Raised when market data operations fail"""
    pass

class ConfigurationError(OpenCTPError):
    """Raised when configuration is invalid"""
    pass