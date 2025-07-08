# -*- coding: utf-8 -*-

"""
OpenCTP SDK - A user-friendly Python SDK for OpenCTP

This SDK provides simplified interfaces for market data and trading operations
using the OpenCTP CTP API, hiding the complexity of the underlying implementation.

Author: OpenCTP SDK Team
License: BSD-3-Clause
"""

__version__ = "1.0.0"
__author__ = "OpenCTP SDK Team"

try:
    from .market_gateway import MarketDataGateway
    from .trading_gateway import TradingGateway
except ImportError as e:
    import warnings
    warnings.warn(f"Failed to import gateways: {e}. Please ensure OpenCTP is properly installed.")
    MarketDataGateway = None
    TradingGateway = None
from .common.types import *
from .common.exceptions import *

__all__ = [
    "MarketDataGateway",
    "TradingGateway", 
    "MarketData",
    "OrderInfo",
    "PositionInfo",
    "AccountInfo",
    "OpenCTPError",
    "ConnectionError", 
    "AuthenticationError",
    "TradingError"
]