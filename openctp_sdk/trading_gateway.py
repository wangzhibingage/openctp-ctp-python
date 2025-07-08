# -*- coding: utf-8 -*-

"""
Trading Gateway SDK for OpenCTP

Provides a simplified interface for trading operations including:
- Authentication and login
- Order management 
- Position and account queries
- Real-time trading updates

Author: OpenCTP SDK Team
"""

import threading
import time
from typing import List, Optional, Dict, Any, Callable
import logging

from .common.utils import setup_logger, add_ctp_library_path, safe_float, safe_int, safe_str
from .common.types import (
    Direction, Offset, PriceType, OrderStatus,
    OrderInfo, PositionInfo, AccountInfo,
    OrderCallback, PositionCallback, AccountCallback, 
    ConnectionCallback, DisconnectionCallback, ErrorCallback
)
from .common.exceptions import ConnectionError, AuthenticationError, TradingError, ConfigurationError

# Add CTP library path
add_ctp_library_path()

try:
    from openctp_ctp import tdapi
except ImportError:
    try:
        import thosttraderapi as tdapi
    except ImportError:
        raise ImportError("Failed to import trading API. Please ensure OpenCTP is properly installed.")

class TradingGateway:
    """
    Trading Gateway for simplified trading operations
    
    This class provides a user-friendly interface for connecting to CTP trading server,
    managing orders, querying positions and account information.
    
    Example:
        ```python
        def on_order_update(order: OrderInfo):
            print(f"Order update: {order.instrument_id} - {order.order_status}")
        
        gateway = TradingGateway(
            front_address="tcp://180.168.146.187:10130",
            broker_id="9999",
            user_id="000001", 
            password="888888",
            app_id="simnow_client_test",
            auth_code="0000000000000000"
        )
        gateway.set_order_callback(on_order_update)
        gateway.connect()
        
        # Place an order
        order_ref = gateway.place_order(
            instrument_id="au2406",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=500.0,
            volume=1
        )
        
        # Keep running
        input("Press Enter to exit...")
        gateway.disconnect()
        ```
    """
    
    def __init__(self, front_address: str, broker_id: str, user_id: str, password: str,
                 app_id: str = "", auth_code: str = "", auto_reconnect: bool = True):
        """
        Initialize Trading Gateway
        
        Args:
            front_address: Trading server address (e.g., "tcp://180.168.146.187:10130")
            broker_id: Broker ID
            user_id: User ID
            password: Password
            app_id: Application ID (for authentication)
            auth_code: Auth code (for authentication)
            auto_reconnect: Enable automatic reconnection
        """
        # Configuration
        self.front_address = front_address
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password
        self.app_id = app_id
        self.auth_code = auth_code
        self.auto_reconnect = auto_reconnect
        
        # Internal state
        self._api: Optional[tdapi.CThostFtdcTraderApi] = None
        self._spi: Optional['_TradingSpi'] = None
        self._connected = False
        self._authenticated = False
        self._logged_in = False
        self._settlement_confirmed = False
        
        # Trading session info
        self.trading_day = ""
        self.front_id = 0
        self.session_id = 0
        self.order_ref = 1
        self.max_order_ref = 0
        
        # Data caches
        self._orders: Dict[str, OrderInfo] = {}
        self._positions: Dict[str, PositionInfo] = {}
        self._account: Optional[AccountInfo] = None
        
        # Synchronization
        self._request_id = 0
        self._request_lock = threading.Lock()
        self._response_events: Dict[int, threading.Event] = {}
        self._response_data: Dict[int, Any] = {}
        
        # Callbacks
        self._order_callback: Optional[OrderCallback] = None
        self._position_callback: Optional[PositionCallback] = None
        self._account_callback: Optional[AccountCallback] = None
        self._connection_callback: Optional[ConnectionCallback] = None
        self._disconnection_callback: Optional[DisconnectionCallback] = None
        self._error_callback: Optional[ErrorCallback] = None
        
        # Logger
        self.logger = setup_logger(f"TradingGateway.{id(self)}")
        
        # Validation
        if not all([front_address, broker_id, user_id, password]):
            raise ConfigurationError("Front address, broker ID, user ID and password are required")
    
    def set_order_callback(self, callback: OrderCallback) -> None:
        """Set callback for order updates"""
        self._order_callback = callback
    
    def set_position_callback(self, callback: PositionCallback) -> None:
        """Set callback for position updates"""
        self._position_callback = callback
    
    def set_account_callback(self, callback: AccountCallback) -> None:
        """Set callback for account updates"""
        self._account_callback = callback
    
    def set_connection_callback(self, callback: ConnectionCallback) -> None:
        """Set callback for connection events"""
        self._connection_callback = callback
    
    def set_disconnection_callback(self, callback: DisconnectionCallback) -> None:
        """Set callback for disconnection events"""
        self._disconnection_callback = callback
    
    def set_error_callback(self, callback: ErrorCallback) -> None:
        """Set callback for error events"""
        self._error_callback = callback
    
    def connect(self, timeout: float = 30.0) -> None:
        """
        Connect to trading server and complete authentication
        
        Args:
            timeout: Total connection timeout in seconds
            
        Raises:
            ConnectionError: If connection fails
            AuthenticationError: If authentication fails
        """
        try:
            self.logger.info(f"Connecting to trading server: {self.front_address}")
            
            # Create API and SPI
            self._api = tdapi.CThostFtdcTraderApi.CreateFtdcTraderApi()
            self._spi = _TradingSpi(self)
            self._api.RegisterSpi(self._spi)
            self._api.RegisterFront(self.front_address)
            
            # Subscribe to private and public topics
            self._api.SubscribePrivateTopic(tdapi.THOST_TERT_QUICK)
            self._api.SubscribePublicTopic(tdapi.THOST_TERT_QUICK)
            
            # Initialize connection
            self._api.Init()
            
            # Wait for full connection sequence (connect -> auth -> login -> settlement)
            start_time = time.time()
            while (not self._settlement_confirmed and 
                   time.time() - start_time < timeout):
                time.sleep(0.1)
            
            if not self._settlement_confirmed:
                status = self._get_connection_status()
                raise ConnectionError(f"Failed to complete connection sequence within {timeout} seconds. Status: {status}")
                
            self.logger.info("Successfully connected and authenticated to trading server")
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            if isinstance(e, (ConnectionError, AuthenticationError)):
                raise
            else:
                raise ConnectionError(f"Failed to connect: {e}")
    
    def disconnect(self) -> None:
        """Disconnect from trading server"""
        try:
            self.logger.info("Disconnecting from trading server")
            
            if self._api:
                self._api.Release()
                self._api = None
            
            self._spi = None
            self._connected = False
            self._authenticated = False
            self._logged_in = False
            self._settlement_confirmed = False
            
            # Clear caches
            self._orders.clear()
            self._positions.clear()
            self._account = None
            
            # Clear response events
            self._response_events.clear()
            self._response_data.clear()
            
            self.logger.info("Successfully disconnected from trading server")
            
        except Exception as e:
            self.logger.error(f"Error during disconnect: {e}")
    
    def place_order(self, instrument_id: str, direction: Direction, offset: Offset,
                   price: float, volume: int, price_type: PriceType = PriceType.LIMIT_PRICE,
                   exchange_id: str = "") -> str:
        """
        Place a new order
        
        Args:
            instrument_id: Instrument ID
            direction: Order direction (BUY/SELL)
            offset: Order offset (OPEN/CLOSE/etc.)
            price: Order price
            volume: Order volume
            price_type: Price type (default: LIMIT_PRICE)
            exchange_id: Exchange ID (optional, will be auto-detected if empty)
            
        Returns:
            Order reference string
            
        Raises:
            TradingError: If order placement fails
        """
        if not self._settlement_confirmed:
            raise TradingError("Not ready for trading - connection not fully established")
        
        try:
            # Generate order ref
            order_ref = str(self.order_ref)
            self.order_ref += 1
            
            # Create order request
            req = tdapi.CThostFtdcInputOrderField()
            req.BrokerID = self.broker_id
            req.InvestorID = self.user_id
            req.OrderRef = order_ref
            req.UserID = self.user_id
            req.InstrumentID = instrument_id
            req.ExchangeID = exchange_id
            req.Direction = direction.value
            req.CombOffsetFlag = offset.value
            req.CombHedgeFlag = "1"  # Speculation
            req.LimitPrice = price
            req.VolumeTotalOriginal = volume
            req.OrderPriceType = price_type.value
            req.TimeCondition = "3"  # GFD (Good For Day)
            req.VolumeCondition = "1"  # Any volume
            req.MinVolume = 1
            req.ContingentCondition = "1"  # Immediately
            req.StopPrice = 0
            req.ForceCloseReason = "0"  # Not force close
            req.IsAutoSuspend = 0
            
            self.logger.info(f"Placing order: {instrument_id} {direction.name} {offset.name} "
                           f"Price={price} Volume={volume} Ref={order_ref}")
            
            # Send order
            request_id = self._get_next_request_id()
            ret = self._api.ReqOrderInsert(req, request_id)
            
            if ret != 0:
                raise TradingError(f"Failed to send order request, return code: {ret}")
            
            return order_ref
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
            raise TradingError(f"Failed to place order: {e}")
    
    def cancel_order(self, order_ref: str, exchange_id: str = "", order_sys_id: str = "") -> None:
        """
        Cancel an existing order
        
        Args:
            order_ref: Order reference
            exchange_id: Exchange ID (required if order_sys_id provided)
            order_sys_id: System order ID (optional)
            
        Raises:
            TradingError: If order cancellation fails
        """
        if not self._settlement_confirmed:
            raise TradingError("Not ready for trading - connection not fully established")
        
        try:
            # Create cancel request
            req = tdapi.CThostFtdcInputOrderActionField()
            req.BrokerID = self.broker_id
            req.InvestorID = self.user_id
            req.OrderRef = order_ref
            req.FrontID = self.front_id
            req.SessionID = self.session_id
            req.ActionFlag = "0"  # Delete
            
            if exchange_id:
                req.ExchangeID = exchange_id
            if order_sys_id:
                req.OrderSysID = order_sys_id
            
            self.logger.info(f"Canceling order: Ref={order_ref} SysID={order_sys_id}")
            
            # Send cancel request
            request_id = self._get_next_request_id()
            ret = self._api.ReqOrderAction(req, request_id)
            
            if ret != 0:
                raise TradingError(f"Failed to send cancel request, return code: {ret}")
                
        except Exception as e:
            self.logger.error(f"Failed to cancel order: {e}")
            raise TradingError(f"Failed to cancel order: {e}")
    
    def query_orders(self, timeout: float = 10.0) -> List[OrderInfo]:
        """
        Query all orders
        
        Args:
            timeout: Query timeout in seconds
            
        Returns:
            List of order information
            
        Raises:
            TradingError: If query fails
        """
        return self._query_with_timeout(self._query_orders_impl, timeout, "orders")
    
    def query_positions(self, timeout: float = 10.0) -> List[PositionInfo]:
        """
        Query all positions
        
        Args:
            timeout: Query timeout in seconds
            
        Returns:
            List of position information
            
        Raises:
            TradingError: If query fails
        """
        return self._query_with_timeout(self._query_positions_impl, timeout, "positions")
    
    def query_account(self, timeout: float = 10.0) -> AccountInfo:
        """
        Query account information
        
        Args:
            timeout: Query timeout in seconds
            
        Returns:
            Account information
            
        Raises:
            TradingError: If query fails
        """
        return self._query_with_timeout(self._query_account_impl, timeout, "account")
    
    def get_cached_orders(self) -> Dict[str, OrderInfo]:
        """Get cached order information"""
        return self._orders.copy()
    
    def get_cached_positions(self) -> Dict[str, PositionInfo]:
        """Get cached position information"""
        return self._positions.copy()
    
    def get_cached_account(self) -> Optional[AccountInfo]:
        """Get cached account information"""
        return self._account
    
    def is_connected(self) -> bool:
        """Check if connected to server"""
        return self._connected
    
    def is_authenticated(self) -> bool:
        """Check if authenticated"""
        return self._authenticated
    
    def is_logged_in(self) -> bool:
        """Check if logged in"""
        return self._logged_in
    
    def is_ready_for_trading(self) -> bool:
        """Check if ready for trading (settlement confirmed)"""
        return self._settlement_confirmed
    
    def _get_connection_status(self) -> str:
        """Get current connection status for debugging"""
        return (f"Connected: {self._connected}, "
                f"Authenticated: {self._authenticated}, "
                f"LoggedIn: {self._logged_in}, "
                f"SettlementConfirmed: {self._settlement_confirmed}")
    
    def _get_next_request_id(self) -> int:
        """Get next request ID"""
        with self._request_lock:
            self._request_id += 1
            return self._request_id
    
    def _query_with_timeout(self, query_func: Callable, timeout: float, data_type: str) -> Any:
        """Execute query with timeout"""
        if not self._settlement_confirmed:
            raise TradingError("Not ready for trading - connection not fully established")
        
        try:
            request_id = self._get_next_request_id()
            event = threading.Event()
            self._response_events[request_id] = event
            
            # Execute query
            ret = query_func(request_id)
            if ret != 0:
                raise TradingError(f"Failed to send {data_type} query request, return code: {ret}")
            
            # Wait for response
            if not event.wait(timeout):
                raise TradingError(f"{data_type.capitalize()} query timeout after {timeout} seconds")
            
            # Get result
            result = self._response_data.pop(request_id, None)
            self._response_events.pop(request_id, None)
            
            if result is None:
                raise TradingError(f"No {data_type} data received")
                
            return result
            
        except Exception as e:
            # Cleanup
            self._response_events.pop(request_id, None)
            self._response_data.pop(request_id, None)
            
            self.logger.error(f"Failed to query {data_type}: {e}")
            raise TradingError(f"Failed to query {data_type}: {e}")
    
    def _query_orders_impl(self, request_id: int) -> int:
        """Internal implementation for querying orders"""
        req = tdapi.CThostFtdcQryOrderField()
        req.BrokerID = self.broker_id
        req.InvestorID = self.user_id
        return self._api.ReqQryOrder(req, request_id)
    
    def _query_positions_impl(self, request_id: int) -> int:
        """Internal implementation for querying positions"""
        req = tdapi.CThostFtdcQryInvestorPositionField()
        req.BrokerID = self.broker_id
        req.InvestorID = self.user_id
        return self._api.ReqQryInvestorPosition(req, request_id)
    
    def _query_account_impl(self, request_id: int) -> int:
        """Internal implementation for querying account"""
        req = tdapi.CThostFtdcQryTradingAccountField()
        req.BrokerID = self.broker_id
        req.InvestorID = self.user_id
        return self._api.ReqQryTradingAccount(req, request_id)
    
    # Internal callback methods
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
        self._authenticated = False
        self._logged_in = False
        self._settlement_confirmed = False
        
        if self._disconnection_callback:
            try:
                self._disconnection_callback(reason)
            except Exception as e:
                self.logger.error(f"Error in disconnection callback: {e}")
    
    def _on_authenticated(self) -> None:
        """Internal callback for authentication success"""
        self._authenticated = True
        self.logger.info("Successfully authenticated")
    
    def _on_login_success(self, trading_day: str, front_id: int, session_id: int, max_order_ref: str) -> None:
        """Internal callback for login success"""
        self._logged_in = True
        self.trading_day = trading_day
        self.front_id = front_id
        self.session_id = session_id
        self.max_order_ref = safe_int(max_order_ref)
        self.order_ref = max(self.order_ref, self.max_order_ref + 1)
        
        self.logger.info(f"Successfully logged in. Trading day: {trading_day}, "
                        f"FrontID: {front_id}, SessionID: {session_id}, MaxOrderRef: {max_order_ref}")
    
    def _on_settlement_confirmed(self) -> None:
        """Internal callback for settlement confirmation"""
        self._settlement_confirmed = True
        self.logger.info("Settlement information confirmed - ready for trading")
    
    def _on_order_update(self, order: OrderInfo) -> None:
        """Internal callback for order updates"""
        # Cache order
        order_key = f"{order.order_ref}_{order.front_id}_{order.session_id}"
        self._orders[order_key] = order
        
        if self._order_callback:
            try:
                self._order_callback(order)
            except Exception as e:
                self.logger.error(f"Error in order callback: {e}")
    
    def _on_position_update(self, position: PositionInfo) -> None:
        """Internal callback for position updates"""
        # Cache position
        position_key = f"{position.instrument_id}_{position.position_direction}"
        self._positions[position_key] = position
        
        if self._position_callback:
            try:
                self._position_callback(position)
            except Exception as e:
                self.logger.error(f"Error in position callback: {e}")
    
    def _on_account_update(self, account: AccountInfo) -> None:
        """Internal callback for account updates"""
        # Cache account
        self._account = account
        
        if self._account_callback:
            try:
                self._account_callback(account)
            except Exception as e:
                self.logger.error(f"Error in account callback: {e}")
    
    def _on_error(self, message: str, error_code: int) -> None:
        """Internal callback for errors"""
        self.logger.error(f"Error occurred: {message} (Code: {error_code})")
        if self._error_callback:
            try:
                self._error_callback(message, error_code)
            except Exception as e:
                self.logger.error(f"Error in error callback: {e}")
    
    def _set_query_response(self, request_id: int, data: Any) -> None:
        """Set query response data"""
        self._response_data[request_id] = data
        event = self._response_events.get(request_id)
        if event:
            event.set()


class _TradingSpi(tdapi.CThostFtdcTraderSpi):
    """Internal SPI implementation for trading"""
    
    def __init__(self, gateway: TradingGateway):
        super().__init__()
        self.gateway = gateway
        self.logger = gateway.logger
    
    def OnFrontConnected(self) -> "void":
        """Front connected callback"""
        self.logger.debug("OnFrontConnected")
        self.gateway._on_connected()
        
        # Start authentication if credentials provided
        if self.gateway.app_id and self.gateway.auth_code:
            req = tdapi.CThostFtdcReqAuthenticateField()
            req.BrokerID = self.gateway.broker_id
            req.UserID = self.gateway.user_id
            req.AppID = self.gateway.app_id
            req.AuthCode = self.gateway.auth_code
            
            self.gateway._api.ReqAuthenticate(req, self.gateway._get_next_request_id())
        else:
            # Skip authentication, go directly to login
            self._do_login()
    
    def OnFrontDisconnected(self, nReason: int) -> "void":
        """Front disconnected callback"""
        self.logger.debug(f"OnFrontDisconnected: {nReason}")
        self.gateway._on_disconnected(nReason)
    
    def OnRspAuthenticate(self, pRspAuthenticateField, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Authentication response callback"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Authentication failed: {error_msg}")
            self.gateway._on_error(f"Authentication failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        self.logger.info("Authentication successful")
        self.gateway._on_authenticated()
        
        # Proceed to login
        self._do_login()
    
    def _do_login(self) -> None:
        """Perform login"""
        req = tdapi.CThostFtdcReqUserLoginField()
        req.BrokerID = self.gateway.broker_id
        req.UserID = self.gateway.user_id
        req.Password = self.gateway.password
        req.UserProductInfo = "openctp_sdk"
        
        self.gateway._api.ReqUserLogin(req, self.gateway._get_next_request_id())
    
    def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Login response callback"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Login failed: {error_msg}")
            self.gateway._on_error(f"Login failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        if pRspUserLogin:
            trading_day = safe_str(pRspUserLogin.TradingDay)
            front_id = safe_int(pRspUserLogin.FrontID)
            session_id = safe_int(pRspUserLogin.SessionID)
            max_order_ref = safe_str(pRspUserLogin.MaxOrderRef)
            
            self.gateway._on_login_success(trading_day, front_id, session_id, max_order_ref)
            
            # Query and confirm settlement info
            self._query_settlement_info()
    
    def _query_settlement_info(self) -> None:
        """Query settlement information"""
        req = tdapi.CThostFtdcQrySettlementInfoField()
        req.BrokerID = self.gateway.broker_id
        req.InvestorID = self.gateway.user_id
        req.TradingDay = self.gateway.trading_day
        
        self.gateway._api.ReqQrySettlementInfo(req, self.gateway._get_next_request_id())
    
    def OnRspQrySettlementInfo(self, pSettlementInfo, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Settlement info query response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Query settlement info failed: {error_msg}")
            self.gateway._on_error(f"Query settlement info failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        if bIsLast:
            # Confirm settlement info
            req = tdapi.CThostFtdcSettlementInfoConfirmField()
            req.BrokerID = self.gateway.broker_id
            req.InvestorID = self.gateway.user_id
            
            self.gateway._api.ReqSettlementInfoConfirm(req, self.gateway._get_next_request_id())
    
    def OnRspSettlementInfoConfirm(self, pSettlementInfoConfirm, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Settlement info confirmation response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Settlement info confirmation failed: {error_msg}")
            self.gateway._on_error(f"Settlement info confirmation failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        self.gateway._on_settlement_confirmed()
    
    def OnRspOrderInsert(self, pInputOrder, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Order insert response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            instrument_id = safe_str(pInputOrder.InstrumentID if pInputOrder else "")
            self.logger.error(f"Order insert failed for {instrument_id}: {error_msg}")
            self.gateway._on_error(f"Order insert failed for {instrument_id}: {error_msg}", pRspInfo.ErrorID)
    
    def OnRspOrderAction(self, pInputOrderAction, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Order action response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            order_ref = safe_str(pInputOrderAction.OrderRef if pInputOrderAction else "")
            self.logger.error(f"Order action failed for ref {order_ref}: {error_msg}")
            self.gateway._on_error(f"Order action failed for ref {order_ref}: {error_msg}", pRspInfo.ErrorID)
    
    def OnRtnOrder(self, pOrder) -> "void":
        """Order status update callback"""
        if not pOrder:
            return
        
        try:
            order = self._convert_order(pOrder)
            self.gateway._on_order_update(order)
        except Exception as e:
            self.logger.error(f"Error processing order update: {e}")
    
    def OnRspQryOrder(self, pOrder, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Order query response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Order query failed: {error_msg}")
            self.gateway._on_error(f"Order query failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        # Collect orders
        if not hasattr(self, '_temp_orders'):
            self._temp_orders = []
        
        if pOrder:
            try:
                order = self._convert_order(pOrder)
                self._temp_orders.append(order)
            except Exception as e:
                self.logger.error(f"Error converting order: {e}")
        
        if bIsLast:
            self.gateway._set_query_response(nRequestID, self._temp_orders)
            delattr(self, '_temp_orders')
    
    def OnRspQryInvestorPosition(self, pInvestorPosition, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Position query response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Position query failed: {error_msg}")
            self.gateway._on_error(f"Position query failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        # Collect positions
        if not hasattr(self, '_temp_positions'):
            self._temp_positions = []
        
        if pInvestorPosition:
            try:
                position = self._convert_position(pInvestorPosition)
                self._temp_positions.append(position)
            except Exception as e:
                self.logger.error(f"Error converting position: {e}")
        
        if bIsLast:
            self.gateway._set_query_response(nRequestID, self._temp_positions)
            delattr(self, '_temp_positions')
    
    def OnRspQryTradingAccount(self, pTradingAccount, pRspInfo, nRequestID: int, bIsLast: bool) -> "void":
        """Account query response"""
        if pRspInfo and pRspInfo.ErrorID != 0:
            error_msg = safe_str(pRspInfo.ErrorMsg, "Unknown error")
            self.logger.error(f"Account query failed: {error_msg}")
            self.gateway._on_error(f"Account query failed: {error_msg}", pRspInfo.ErrorID)
            return
        
        if pTradingAccount:
            try:
                account = self._convert_account(pTradingAccount)
                self.gateway._set_query_response(nRequestID, account)
            except Exception as e:
                self.logger.error(f"Error converting account: {e}")
    
    def _convert_order(self, pOrder) -> OrderInfo:
        """Convert CTP order to OrderInfo"""
        return OrderInfo(
            broker_id=safe_str(pOrder.BrokerID),
            investor_id=safe_str(pOrder.InvestorID),
            order_ref=safe_str(pOrder.OrderRef),
            user_id=safe_str(pOrder.UserID),
            order_price_type=safe_str(pOrder.OrderPriceType),
            direction=safe_str(pOrder.Direction),
            combine_offset_flag=safe_str(pOrder.CombOffsetFlag),
            combine_hedge_flag=safe_str(pOrder.CombHedgeFlag),
            limit_price=safe_float(pOrder.LimitPrice),
            volume_total_original=safe_int(pOrder.VolumeTotalOriginal),
            time_condition=safe_str(pOrder.TimeCondition),
            gtd_date=safe_str(pOrder.GTDDate),
            volume_condition=safe_str(pOrder.VolumeCondition),
            min_volume=safe_int(pOrder.MinVolume),
            contingent_condition=safe_str(pOrder.ContingentCondition),
            stop_price=safe_float(pOrder.StopPrice),
            force_close_reason=safe_str(pOrder.ForceCloseReason),
            is_auto_suspend=safe_int(pOrder.IsAutoSuspend),
            business_unit=safe_str(pOrder.BusinessUnit),
            request_id=safe_int(pOrder.RequestID),
            order_local_id=safe_str(pOrder.OrderLocalID),
            exchange_id=safe_str(pOrder.ExchangeID),
            participant_id=safe_str(pOrder.ParticipantID),
            client_id=safe_str(pOrder.ClientID),
            exchange_inst_id=safe_str(pOrder.ExchangeInstID),
            trader_id=safe_str(pOrder.TraderID),
            install_id=safe_int(pOrder.InstallID),
            order_submit_status=safe_str(pOrder.OrderSubmitStatus),
            notify_sequence=safe_int(pOrder.NotifySequence),
            trading_day=safe_str(pOrder.TradingDay),
            settlement_id=safe_int(pOrder.SettlementID),
            order_sys_id=safe_str(pOrder.OrderSysID),
            order_source=safe_str(pOrder.OrderSource),
            order_status=safe_str(pOrder.OrderStatus),
            order_type=safe_str(pOrder.OrderType),
            volume_traded=safe_int(pOrder.VolumeTraded),
            volume_total=safe_int(pOrder.VolumeTotal),
            insert_date=safe_str(pOrder.InsertDate),
            insert_time=safe_str(pOrder.InsertTime),
            active_time=safe_str(pOrder.ActiveTime),
            suspend_time=safe_str(pOrder.SuspendTime),
            update_time=safe_str(pOrder.UpdateTime),
            cancel_time=safe_str(pOrder.CancelTime),
            active_trader_id=safe_str(pOrder.ActiveTraderID),
            clearing_part_id=safe_str(pOrder.ClearingPartID),
            sequence_no=safe_int(pOrder.SequenceNo),
            front_id=safe_int(pOrder.FrontID),
            session_id=safe_int(pOrder.SessionID),
            user_product_info=safe_str(pOrder.UserProductInfo),
            status_msg=safe_str(pOrder.StatusMsg),
            user_force_close=safe_int(pOrder.UserForceClose),
            active_user_id=safe_str(pOrder.ActiveUserID),
            broker_order_seq=safe_int(pOrder.BrokerOrderSeq),
            relative_order_sys_id=safe_str(pOrder.RelativeOrderSysID),
            zzce_confirm_id=safe_int(pOrder.ZZCEConfirmID),
            is_swap_order=safe_int(pOrder.IsSwapOrder),
            branch_id=safe_str(pOrder.BranchID),
            invest_unit_id=safe_str(pOrder.InvestUnitID),
            account_id=safe_str(pOrder.AccountID),
            currency_id=safe_str(pOrder.CurrencyID),
            ip_address=safe_str(pOrder.IPAddress),
            mac_address=safe_str(pOrder.MacAddress),
            instrument_id=safe_str(pOrder.InstrumentID)
        )
    
    def _convert_position(self, pPosition) -> PositionInfo:
        """Convert CTP position to PositionInfo"""
        return PositionInfo(
            broker_id=safe_str(pPosition.BrokerID),
            investor_id=safe_str(pPosition.InvestorID),
            instrument_id=safe_str(pPosition.InstrumentID),
            position_direction=safe_str(pPosition.PosiDirection),
            hedge_flag=safe_str(pPosition.HedgeFlag),
            position_date=safe_str(pPosition.PositionDate),
            yd_position=safe_int(pPosition.YdPosition),
            position=safe_int(pPosition.Position),
            long_frozen=safe_int(pPosition.LongFrozen),
            short_frozen=safe_int(pPosition.ShortFrozen),
            long_frozen_amount=safe_float(pPosition.LongFrozenAmount),
            short_frozen_amount=safe_float(pPosition.ShortFrozenAmount),
            open_volume=safe_int(pPosition.OpenVolume),
            close_volume=safe_int(pPosition.CloseVolume),
            open_amount=safe_float(pPosition.OpenAmount),
            close_amount=safe_float(pPosition.CloseAmount),
            position_cost=safe_float(pPosition.PositionCost),
            pre_margin=safe_float(pPosition.PreMargin),
            use_margin=safe_float(pPosition.UseMargin),
            frozen_margin=safe_float(pPosition.FrozenMargin),
            frozen_cash=safe_float(pPosition.FrozenCash),
            frozen_commission=safe_float(pPosition.FrozenCommission),
            cash_in=safe_float(pPosition.CashIn),
            commission=safe_float(pPosition.Commission),
            close_profit=safe_float(pPosition.CloseProfit),
            position_profit=safe_float(pPosition.PositionProfit),
            pre_settlement_price=safe_float(pPosition.PreSettlementPrice),
            settlement_price=safe_float(pPosition.SettlementPrice),
            trading_day=safe_str(pPosition.TradingDay),
            settlement_id=safe_int(pPosition.SettlementID),
            open_cost=safe_float(pPosition.OpenCost),
            exchange_margin=safe_float(pPosition.ExchangeMargin),
            combine_position=safe_int(pPosition.CombPosition),
            combine_long_frozen=safe_int(pPosition.CombLongFrozen),
            combine_short_frozen=safe_int(pPosition.CombShortFrozen),
            close_profit_by_date=safe_float(pPosition.CloseProfitByDate),
            close_profit_by_trade=safe_float(pPosition.CloseProfitByTrade),
            today_position=safe_int(pPosition.TodayPosition),
            margin_rate_by_money=safe_float(pPosition.MarginRateByMoney),
            margin_rate_by_volume=safe_float(pPosition.MarginRateByVolume),
            strike_frozen=safe_int(pPosition.StrikeFrozen),
            strike_frozen_amount=safe_float(pPosition.StrikeFrozenAmount),
            abandon_frozen=safe_int(pPosition.AbandonFrozen),
            exchange_id=safe_str(pPosition.ExchangeID),
            yd_strike_frozen=safe_int(pPosition.YdStrikeFrozen),
            invest_unit_id=safe_str(pPosition.InvestUnitID),
            position_cost_offset=safe_float(pPosition.PositionCostOffset)
        )
    
    def _convert_account(self, pAccount) -> AccountInfo:
        """Convert CTP account to AccountInfo"""
        return AccountInfo(
            broker_id=safe_str(pAccount.BrokerID),
            account_id=safe_str(pAccount.AccountID),
            pre_mortgage=safe_float(pAccount.PreMortgage),
            pre_credit=safe_float(pAccount.PreCredit),
            pre_deposit=safe_float(pAccount.PreDeposit),
            pre_balance=safe_float(pAccount.PreBalance),
            pre_margin=safe_float(pAccount.PreMargin),
            interest_base=safe_float(pAccount.InterestBase),
            interest=safe_float(pAccount.Interest),
            deposit=safe_float(pAccount.Deposit),
            withdraw=safe_float(pAccount.Withdraw),
            frozen_margin=safe_float(pAccount.FrozenMargin),
            frozen_cash=safe_float(pAccount.FrozenCash),
            frozen_commission=safe_float(pAccount.FrozenCommission),
            curr_margin=safe_float(pAccount.CurrMargin),
            cash_in=safe_float(pAccount.CashIn),
            commission=safe_float(pAccount.Commission),
            close_profit=safe_float(pAccount.CloseProfit),
            position_profit=safe_float(pAccount.PositionProfit),
            balance=safe_float(pAccount.Balance),
            available=safe_float(pAccount.Available),
            withdraw_quota=safe_float(pAccount.WithdrawQuota),
            reserve=safe_float(pAccount.Reserve),
            trading_day=safe_str(pAccount.TradingDay),
            settlement_id=safe_int(pAccount.SettlementID),
            credit=safe_float(pAccount.Credit),
            mortgage=safe_float(pAccount.Mortgage),
            exchange_margin=safe_float(pAccount.ExchangeMargin),
            delivery_margin=safe_float(pAccount.DeliveryMargin),
            exchange_delivery_margin=safe_float(pAccount.ExchangeDeliveryMargin),
            reserve_balance=safe_float(pAccount.ReserveBalance),
            currency_id=safe_str(pAccount.CurrencyID),
            pre_fund_mortgage_in=safe_float(pAccount.PreFundMortgageIn),
            pre_fund_mortgage_out=safe_float(pAccount.PreFundMortgageOut),
            fund_mortgage_in=safe_float(pAccount.FundMortgageIn),
            fund_mortgage_out=safe_float(pAccount.FundMortgageOut),
            fund_mortgage_available=safe_float(pAccount.FundMortgageAvailable),
            mortgage_able_fund=safe_float(pAccount.MortgageableFund),
            spec_product_margin=safe_float(pAccount.SpecProductMargin),
            spec_product_frozen_margin=safe_float(pAccount.SpecProductFrozenMargin),
            spec_product_commission=safe_float(pAccount.SpecProductCommission),
            spec_product_frozen_commission=safe_float(pAccount.SpecProductFrozenCommission),
            spec_product_position_profit=safe_float(pAccount.SpecProductPositionProfit),
            spec_product_close_profit=safe_float(pAccount.SpecProductCloseProfit),
            spec_product_position_profit_by_algorithm=safe_float(pAccount.SpecProductPositionProfitByAlgorithm),
            spec_product_exchange_margin=safe_float(pAccount.SpecProductExchangeMargin),
            biz_type=safe_str(pAccount.BizType),
            frozen_swap=safe_float(pAccount.FrozenSwap),
            remain_swap=safe_float(pAccount.RemainSwap)
        )