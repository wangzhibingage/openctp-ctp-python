# -*- coding: utf-8 -*-

"""
Market Data Gateway SDK for OpenCTP

Provides a simplified interface for market data operations including:
- Connection management
- Market data subscription
- Real-time data callbacks
- Error handling

Author: OpenCTP SDK Team
"""

import threading
import time
from typing import List, Optional, Dict, Any, Callable
import logging

from .common.utils import setup_logger, add_ctp_library_path, safe_float, safe_int, safe_str
from .common.types import MarketData, MarketDataCallback, ConnectionCallback, DisconnectionCallback, ErrorCallback
from .common.exceptions import ConnectionError, MarketDataError, ConfigurationError

# Add CTP library path
add_ctp_library_path()

try:
    import thostmduserapi as mdapi
except ImportError:
    raise ImportError("Failed to import thostmduserapi. Please ensure OpenCTP is properly installed.")

class MarketDataGateway:
    """
    Market Data Gateway for simplified market data operations
    
    This class provides a user-friendly interface for connecting to CTP market data server,
    subscribing to market data, and handling real-time updates.
    
    Example:
        ```python
        def on_market_data(data: MarketData):
            print(f"Received data for {data.instrument_id}: {data.last_price}")
        
        gateway = MarketDataGateway("tcp://180.168.146.187:10131")
        gateway.set_market_data_callback(on_market_data)
        gateway.connect()
        gateway.subscribe(["au2406", "ag2406"])
        
        # Keep running
        input("Press Enter to exit...")
        gateway.disconnect()
        ```
    """
    
    def __init__(self, front_address: str, user_id: str = "", password: str = "", 
                 broker_id: str = "", auto_reconnect: bool = True):
        """
        Initialize Market Data Gateway
        
        Args:
            front_address: Market data server address (e.g., "tcp://180.168.146.187:10131")
            user_id: User ID (optional for market data)
            password: Password (optional for market data)
            broker_id: Broker ID (optional for market data)
            auto_reconnect: Enable automatic reconnection
        """
        self.front_address = front_address
        self.user_id = user_id
        self.password = password
        self.broker_id = broker_id
        self.auto_reconnect = auto_reconnect
        
        # Internal state
        self._api: Optional[mdapi.CThostFtdcMdApi] = None
        self._spi: Optional['_MarketDataSpi'] = None
        self._connected = False
        self._logged_in = False
        self._subscribed_instruments: Dict[str, bool] = {}
        self._reconnect_thread: Optional[threading.Thread] = None
        self._should_stop = False
        
        # Callbacks
        self._market_data_callback: Optional[MarketDataCallback] = None
        self._connection_callback: Optional[ConnectionCallback] = None
        self._disconnection_callback: Optional[DisconnectionCallback] = None
        self._error_callback: Optional[ErrorCallback] = None
        
        # Logger
        self.logger = setup_logger(f"MarketDataGateway.{id(self)}")
        
        # Validation
        if not front_address:
            raise ConfigurationError("Front address is required")
    
    def set_market_data_callback(self, callback: MarketDataCallback) -> None:
        """Set callback for market data updates"""
        self._market_data_callback = callback
    
    def set_connection_callback(self, callback: ConnectionCallback) -> None:
        """Set callback for connection events"""
        self._connection_callback = callback
    
    def set_disconnection_callback(self, callback: DisconnectionCallback) -> None:
        """Set callback for disconnection events"""
        self._disconnection_callback = callback
    
    def set_error_callback(self, callback: ErrorCallback) -> None:
        """Set callback for error events"""
        self._error_callback = callback
    
    def connect(self, timeout: float = 10.0) -> None:
        """
        Connect to market data server
        
        Args:
            timeout: Connection timeout in seconds
            
        Raises:
            ConnectionError: If connection fails
        """
        try:
            self.logger.info(f"Connecting to market data server: {self.front_address}")
            
            # Create API and SPI
            self._api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi()
            self._spi = _MarketDataSpi(self)
            self._api.RegisterSpi(self._spi)
            self._api.RegisterFront(self.front_address)
            
            # Initialize connection
            self._api.Init()
            
            # Wait for connection
            start_time = time.time()
            while not self._connected and time.time() - start_time < timeout:
                time.sleep(0.1)
            
            if not self._connected:
                raise ConnectionError(f"Failed to connect within {timeout} seconds")
                
            self.logger.info("Successfully connected to market data server")
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise ConnectionError(f"Failed to connect: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from market data server"""
        try:
            self.logger.info("Disconnecting from market data server")
            self._should_stop = True
            
            if self._api:
                self._api.Release()
                self._api = None
            
            self._spi = None
            self._connected = False
            self._logged_in = False
            self._subscribed_instruments.clear()
            
            self.logger.info("Successfully disconnected from market data server")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    def subscribe(self, instruments: List[str]) -> None:
        """
        Subscribe to market data for specified instruments
        
        Args:
            instruments: List of instrument IDs to subscribe
            
        Raises:
            MarketDataError: If subscription fails
        """
        if not self._logged_in:
            raise MarketDataError("Not logged in, cannot subscribe to market data")
        
        if not instruments:
            raise MarketDataError("No instruments specified for subscription")
        
        try:
            # Convert to bytes array as required by CTP API
            instrument_bytes = [inst.encode('utf-8') for inst in instruments]
            
            self.logger.info(f"Subscribing to market data for: {instruments}")
            ret = self._api.SubscribeMarketData(instrument_bytes, len(instruments))
            
            if ret != 0:
                raise MarketDataError(f"Failed to subscribe market data, return code: {ret}")
            
            # Track subscribed instruments
            for instrument in instruments:
                self._subscribed_instruments[instrument] = False  # Will be set to True on success callback
                
        except Exception as e:
            self.logger.error(f"Failed to subscribe market data: {e}")
            raise MarketDataError(f"Failed to subscribe market data: {e}")
    
    def unsubscribe(self, instruments: List[str]) -> None:
        """
        Unsubscribe from market data for specified instruments
        
        Args:
            instruments: List of instrument IDs to unsubscribe
            
        Raises:
            MarketDataError: If unsubscription fails
        """
        if not self._logged_in:
            raise MarketDataError("Not logged in, cannot unsubscribe from market data")
        
        if not instruments:
            return
        
        try:
            # Convert to bytes array as required by CTP API
            instrument_bytes = [inst.encode('utf-8') for inst in instruments]
            
            self.logger.info(f"Unsubscribing from market data for: {instruments}")
            ret = self._api.UnSubscribeMarketData(instrument_bytes, len(instruments))
            
            if ret != 0:
                raise MarketDataError(f"Failed to unsubscribe market data, return code: {ret}")
            
            # Remove from tracking
            for instrument in instruments:
                self._subscribed_instruments.pop(instrument, None)
                
        except Exception as e:
            self.logger.error(f"Failed to unsubscribe market data: {e}")
            raise MarketDataError(f"Failed to unsubscribe market data: {e}")
    
    def get_subscribed_instruments(self) -> List[str]:
        """Get list of currently subscribed instruments"""
        return list(self._subscribed_instruments.keys())
    
    def is_connected(self) -> bool:
        """Check if connected to server"""
        return self._connected
    
    def is_logged_in(self) -> bool:
        """Check if logged in"""
        return self._logged_in
    
    def _on_connected(self) -> None:
        """Internal callback for connection"""
        self._connected = True
        if self._connection_callback:
            try:
                self._connection_callback()
            except Exception as e:
                self.logger.error(f"Error in connection callback: {e}")
    
    def _on_disconnected(self, reason: int) -> None:
        """Internal callback for disconnection"""
        self._connected = False
        self._logged_in = False
        
        if self._disconnection_callback:
            try:
                self._disconnection_callback(reason)
            except Exception as e:
                self.logger.error(f"Error in disconnection callback: {e}")
        
        # Auto reconnect if enabled
        if self.auto_reconnect and not self._should_stop:
            self._start_reconnect()
    
    def _on_login_success(self) -> None:
        """Internal callback for login success"""
        self._logged_in = True
        self.logger.info("Successfully logged in to market data server")
    
    def _on_market_data(self, data: MarketData) -> None:
        """Internal callback for market data"""
        if self._market_data_callback:
            try:
                self._market_data_callback(data)
            except Exception as e:
                self.logger.error(f"Error in market data callback: {e}")
    
    def _on_subscription_success(self, instrument_id: str) -> None:
        """Internal callback for subscription success"""
        self._subscribed_instruments[instrument_id] = True
        self.logger.info(f"Successfully subscribed to market data for: {instrument_id}")
    
    def _on_error(self, message: str, error_code: int) -> None:
        """Internal callback for errors"""
        self.logger.error(f"Error occurred: {message} (Code: {error_code})")
        if self._error_callback:
            try:
                self._error_callback(message, error_code)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")
    
    def _start_reconnect(self) -> None:
        """Start reconnection in background thread"""
        if self._reconnect_thread and self._reconnect_thread.is_alive():
            return
        
        self._reconnect_thread = threading.Thread(target=self._reconnect_loop, daemon=True)
        self._reconnect_thread.start()
    
    def _reconnect_loop(self) -> None:
        """Reconnection loop"""
        reconnect_interval = 5.0
        
        while not self._should_stop and not self._connected:
            try:
                self.logger.info("Attempting to reconnect...")
                self.connect(timeout=5.0)
                
                # Re-subscribe to instruments if connected
                if self._connected and self._subscribed_instruments:
                    instruments = list(self._subscribed_instruments.keys())
                    self.subscribe(instruments)
                    
                break
                
            except Exception as e:
                self.logger.warning(f"Reconnection failed: {e}")
                time.sleep(reconnect_interval)
                reconnect_interval = min(reconnect_interval * 1.5, 60.0)  # Exponential backoff


class _MarketDataSpi(mdapi.CThostFtdcMdSpi):
    """Internal SPI implementation for market data"""
    
    def __init__(self, gateway: MarketDataGateway):
        super().__init__()
        self.gateway = gateway
        self.logger = gateway.logger
    
    def OnFrontConnected(self) -> "void":
        """Front connected callback"""
        self.logger.debug("OnFrontConnected")
        self.gateway._on_connected()
        
        # Login (market data doesn't require user credentials)
        req = mdapi.CThostFtdcReqUserLoginField()
        if self.gateway.broker_id:
            req.BrokerID = self.gateway.broker_id
        if self.gateway.user_id:
            req.UserID = self.gateway.user_id
        if self.gateway.password:
            req.Password = self.gateway.password
            
        self.gateway._api.ReqUserLogin(req, 0)
    
    def OnFrontDisconnected(self, nReason: int) -> "void":
        """Front disconnected callback"""
        self.logger.debug(f"OnFrontDisconnected: {nReason}")
        self.gateway._on_disconnected(nReason)
    
    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Login response callback"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Login failed: {error_msg}")
            self.gateway._on_error(f"Login failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        trading_day = safe_str(pRspUserLogin.TradingDay if pRspUserLogin else "")
        self.logger.info(f"Login successful. Trading day: {trading_day}")
        self.gateway._on_login_success()
    
    def OnRtnDepthMarketData(self, pDepthMarketData) -> "void":
        """Market data callback"""
        if not pDepthMarketData:
            return
        
        try:
            # Convert CTP market data to our MarketData structure
            data = MarketData(
                instrument_id=safe_str(pDepthMarketData.InstrumentID),
                exchange_id=safe_str(pDepthMarketData.ExchangeID),
                last_price=safe_float(pDepthMarketData.LastPrice),
                pre_settlement_price=safe_float(pDepthMarketData.PreSettlementPrice),
                pre_close_price=safe_float(pDepthMarketData.PreClosePrice),
                pre_open_interest=safe_float(pDepthMarketData.PreOpenInterest),
                open_price=safe_float(pDepthMarketData.OpenPrice),
                highest_price=safe_float(pDepthMarketData.HighestPrice),
                lowest_price=safe_float(pDepthMarketData.LowestPrice),
                volume=safe_int(pDepthMarketData.Volume),
                turnover=safe_float(pDepthMarketData.Turnover),
                open_interest=safe_float(pDepthMarketData.OpenInterest),
                close_price=safe_float(pDepthMarketData.ClosePrice),
                settlement_price=safe_float(pDepthMarketData.SettlementPrice),
                upper_limit_price=safe_float(pDepthMarketData.UpperLimitPrice),
                lower_limit_price=safe_float(pDepthMarketData.LowerLimitPrice),
                pre_delta=safe_float(pDepthMarketData.PreDelta),
                curr_delta=safe_float(pDepthMarketData.CurrDelta),
                update_time=safe_str(pDepthMarketData.UpdateTime),
                update_millisec=safe_int(pDepthMarketData.UpdateMillisec),
                bid_price1=safe_float(pDepthMarketData.BidPrice1),
                bid_volume1=safe_int(pDepthMarketData.BidVolume1),
                ask_price1=safe_float(pDepthMarketData.AskPrice1),
                ask_volume1=safe_int(pDepthMarketData.AskVolume1),
                bid_price2=safe_float(getattr(pDepthMarketData, 'BidPrice2', 0)),
                bid_volume2=safe_int(getattr(pDepthMarketData, 'BidVolume2', 0)),
                ask_price2=safe_float(getattr(pDepthMarketData, 'AskPrice2', 0)),
                ask_volume2=safe_int(getattr(pDepthMarketData, 'AskVolume2', 0)),
                bid_price3=safe_float(getattr(pDepthMarketData, 'BidPrice3', 0)),
                bid_volume3=safe_int(getattr(pDepthMarketData, 'BidVolume3', 0)),
                ask_price3=safe_float(getattr(pDepthMarketData, 'AskPrice3', 0)),
                ask_volume3=safe_int(getattr(pDepthMarketData, 'AskVolume3', 0)),
                bid_price4=safe_float(getattr(pDepthMarketData, 'BidPrice4', 0)),
                bid_volume4=safe_int(getattr(pDepthMarketData, 'BidVolume4', 0)),
                ask_price4=safe_float(getattr(pDepthMarketData, 'AskPrice4', 0)),
                ask_volume4=safe_int(getattr(pDepthMarketData, 'AskVolume4', 0)),
                bid_price5=safe_float(getattr(pDepthMarketData, 'BidPrice5', 0)),
                bid_volume5=safe_int(getattr(pDepthMarketData, 'BidVolume5', 0)),
                ask_price5=safe_float(getattr(pDepthMarketData, 'AskPrice5', 0)),
                ask_volume5=safe_int(getattr(pDepthMarketData, 'AskVolume5', 0)),
                average_price=safe_float(getattr(pDepthMarketData, 'AveragePrice', 0)),
                action_day=safe_str(getattr(pDepthMarketData, 'ActionDay', "")),
                trading_day=safe_str(getattr(pDepthMarketData, 'TradingDay', ""))
            )
            
            self.gateway._on_market_data(data)
            
        except Exception as e:
            self.logger.error(f"Error processing market data: {e}")
    
    def OnRspSubMarketData(self, pSpecificInstrument, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Market data subscription response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            instrument_id = safe_str(pSpecificInstrument.InstrumentID if pSpecificInstrument else "")
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Subscribe failed for {instrument_id}: {error_msg}")
            self.gateway._on_error(f"Subscribe failed for {instrument_id}: {error_msg}", pRspInfo.ErrorID)
            return
        
        if pSpecificInstrument:
            instrument_id = safe_str(pSpecificInstrument.InstrumentID)
            self.gateway._on_subscription_success(instrument_id)
    
    def OnRspUnSubMarketData(self, pSpecificInstrument, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Market data unsubscription response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            instrument_id = safe_str(pSpecificInstrument.InstrumentID if pSpecificInstrument else "")
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Unsubscribe failed for {instrument_id}: {error_msg}")
            self.gateway._on_error(f"Unsubscribe failed for {instrument_id}: {error_msg}", pRspInfo.ErrorID)
            return
        
        if pSpecificInstrument:
            instrument_id = safe_str(pSpecificInstrument.InstrumentID)
            self.logger.info(f"Successfully unsubscribed from market data for: {instrument_id}")