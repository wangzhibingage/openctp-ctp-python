# OpenCTP SDK - User-Friendly Trading and Market Data SDK

A simplified, user-friendly Python SDK for OpenCTP (China Trading Platform), providing easy-to-use interfaces for market data and trading operations.

## Features

### 🚀 **Easy to Use**
- Simple, intuitive APIs that hide CTP complexity
- Comprehensive examples and documentation
- Type hints for better IDE support
- Automatic connection management and error handling

### 📈 **Market Data Gateway**
- Real-time market data subscription
- Automatic reconnection
- Event-driven callbacks
- Support for multiple instruments

### 💼 **Trading Gateway** 
- Complete trading operations (orders, queries)
- Account and position management
- Real-time order status updates
- Comprehensive error handling

### 🛡️ **Robust & Reliable**
- Automatic reconnection
- Thread-safe operations
- Comprehensive logging
- Custom exception handling

## Quick Start

### Installation

1. Install OpenCTP-CTP:
```bash
pip install openctp-ctp==6.7.2.* -i https://pypi.tuna.tsinghua.edu.cn/simple --trusted-host=pypi.tuna.tsinghua.edu.cn
```

2. Copy the `openctp_sdk` directory to your project.

### Basic Market Data Example

```python
from openctp_sdk import MarketDataGateway, MarketData

def on_market_data(data: MarketData):
    print(f"{data.instrument_id}: {data.last_price}")

# Create and configure gateway
gateway = MarketDataGateway("tcp://180.168.146.187:10131")
gateway.set_market_data_callback(on_market_data)

# Connect and subscribe
gateway.connect()
gateway.subscribe(["au2406", "ag2406"])

# Keep running
input("Press Enter to exit...")
gateway.disconnect()
```

### Basic Trading Example

```python
from openctp_sdk import TradingGateway, Direction, Offset

# Create gateway (replace with your credentials)
gateway = TradingGateway(
    front_address="tcp://180.168.146.187:10130",
    broker_id="9999",
    user_id="000001", 
    password="888888",
    app_id="simnow_client_test",
    auth_code="0000000000000000"
)

# Connect (includes authentication and login)
gateway.connect()

# Query account
account = gateway.query_account()
print(f"Available funds: {account.available}")

# Place an order
order_ref = gateway.place_order(
    instrument_id="au2406",
    direction=Direction.BUY,
    offset=Offset.OPEN,
    price=500.0,
    volume=1
)

print(f"Order placed: {order_ref}")
gateway.disconnect()
```

## SDK Structure

```
openctp_sdk/
├── __init__.py                 # Main SDK entry point
├── market_gateway.py           # Market data gateway
├── trading_gateway.py          # Trading gateway
├── common/
│   ├── __init__.py
│   ├── types.py               # Data structures and enums
│   ├── exceptions.py          # Custom exceptions
│   └── utils.py               # Utility functions
└── examples/
    ├── market_data_example.py  # Market data examples
    ├── trading_example.py      # Trading examples
    ├── complete_example.py     # Complete trading bot
    └── config.json            # Configuration template
```

## API Reference

### MarketDataGateway

#### Constructor
```python
MarketDataGateway(
    front_address: str,          # Market data server address
    user_id: str = "",           # User ID (optional for market data)
    password: str = "",          # Password (optional for market data)
    broker_id: str = "",         # Broker ID (optional for market data)
    auto_reconnect: bool = True  # Enable automatic reconnection
)
```

#### Key Methods
- `connect(timeout: float = 10.0)` - Connect to market data server
- `disconnect()` - Disconnect from server
- `subscribe(instruments: List[str])` - Subscribe to market data
- `unsubscribe(instruments: List[str])` - Unsubscribe from market data
- `set_market_data_callback(callback)` - Set market data callback
- `is_connected() -> bool` - Check connection status

#### Callbacks
```python
def on_market_data(data: MarketData):
    # Handle market data updates
    pass

def on_connected():
    # Handle connection events
    pass

def on_error(message: str, error_code: int):
    # Handle errors
    pass
```

### TradingGateway

#### Constructor
```python
TradingGateway(
    front_address: str,          # Trading server address
    broker_id: str,              # Broker ID
    user_id: str,                # User ID
    password: str,               # Password
    app_id: str = "",            # Application ID
    auth_code: str = "",         # Auth code
    auto_reconnect: bool = True  # Enable automatic reconnection
)
```

#### Key Methods
- `connect(timeout: float = 30.0)` - Connect and authenticate
- `disconnect()` - Disconnect from server
- `place_order(...)` - Place a new order
- `cancel_order(order_ref: str)` - Cancel an order
- `query_orders()` - Query all orders
- `query_positions()` - Query all positions
- `query_account()` - Query account information
- `is_ready_for_trading() -> bool` - Check if ready for trading

#### Order Management
```python
# Place order
order_ref = gateway.place_order(
    instrument_id="au2406",
    direction=Direction.BUY,     # BUY or SELL
    offset=Offset.OPEN,          # OPEN, CLOSE, etc.
    price=500.0,
    volume=1,
    price_type=PriceType.LIMIT_PRICE
)

# Cancel order
gateway.cancel_order(order_ref)
```

### Data Structures

#### MarketData
Contains comprehensive market data including:
- `instrument_id`, `exchange_id`
- `last_price`, `volume`, `turnover`
- `bid_price1`, `bid_volume1`, `ask_price1`, `ask_volume1`
- `update_time`, `trading_day`
- And much more...

#### OrderInfo
Contains complete order information including:
- `order_ref`, `instrument_id`
- `direction`, `offset`, `order_status`
- `limit_price`, `volume_total_original`, `volume_traded`
- `insert_time`, `update_time`
- And much more...

#### PositionInfo
Contains position details including:
- `instrument_id`, `position_direction`
- `position`, `yd_position`, `today_position`
- `position_profit`, `use_margin`
- And much more...

#### AccountInfo
Contains account information including:
- `balance`, `available`, `curr_margin`
- `position_profit`, `close_profit`
- `frozen_margin`, `commission`
- And much more...

### Enums

```python
from openctp_sdk.common import Direction, Offset, PriceType, OrderStatus

# Order direction
Direction.BUY      # "0"
Direction.SELL     # "1"

# Order offset
Offset.OPEN        # "0" - Open position
Offset.CLOSE       # "1" - Close position
Offset.CLOSE_TODAY # "3" - Close today's position

# Price type
PriceType.LIMIT_PRICE  # "2" - Limit price
PriceType.ANY_PRICE    # "1" - Market price

# Order status
OrderStatus.ALL_TRADED      # "0" - Fully filled
OrderStatus.CANCELED        # "5" - Canceled
OrderStatus.NOT_TRADED_QUEUEING  # "3" - Pending
```

## Configuration

### Environment Setup

1. **Install OpenCTP**: Make sure you have the appropriate OpenCTP version installed for your platform.

2. **Server Configuration**: Use the correct server addresses:
   - SimNow Market Data: `tcp://180.168.146.187:10131`
   - SimNow Trading: `tcp://180.168.146.187:10130`

3. **Credentials**: For SimNow demo:
   - Broker ID: `9999`
   - App ID: `simnow_client_test`
   - Auth Code: `0000000000000000`

### Example Configuration File

```json
{
  "market_data": {
    "front_address": "tcp://180.168.146.187:10131",
    "instruments": ["au2406", "ag2406", "cu2406"]
  },
  "trading": {
    "front_address": "tcp://180.168.146.187:10130",
    "broker_id": "9999",
    "user_id": "000001",
    "password": "888888",
    "app_id": "simnow_client_test",
    "auth_code": "0000000000000000"
  }
}
```

## Examples

### 1. Market Data Example
See `examples/market_data_example.py` for a complete market data application.

### 2. Trading Example  
See `examples/trading_example.py` for a complete trading application.

### 3. Complete Trading Bot
See `examples/complete_example.py` for a full trading bot using both gateways.

## Error Handling

The SDK provides comprehensive error handling:

```python
from openctp_sdk.common import OpenCTPError, ConnectionError, TradingError

try:
    gateway.connect()
except ConnectionError as e:
    print(f"Connection failed: {e}")
except AuthenticationError as e:
    print(f"Authentication failed: {e}")
except OpenCTPError as e:
    print(f"SDK error: {e}")
```

## Threading and Callbacks

- All callbacks are called from internal threads
- Callbacks should be thread-safe
- Use logging instead of print() for thread safety
- Long-running operations in callbacks should be avoided

```python
import threading

def on_market_data(data):
    # This runs in an internal thread
    # Keep processing quick or delegate to another thread
    threading.Thread(target=process_data, args=(data,), daemon=True).start()

def process_data(data):
    # Heavy processing here
    pass
```

## Logging

The SDK uses Python's standard logging framework:

```python
from openctp_sdk.common import setup_logger

# Setup custom logger
logger = setup_logger("MyApp", level=logging.INFO, log_file="myapp.log")

# Or use gateway's logger
gateway.logger.info("Custom log message")
```

## Best Practices

### 1. Connection Management
- Always call `disconnect()` when done
- Use try/finally blocks for cleanup
- Handle connection errors gracefully

### 2. Order Management
- Check `is_ready_for_trading()` before placing orders
- Use appropriate price types and offsets
- Implement proper risk management

### 3. Error Handling
- Always handle exceptions in your callbacks
- Log errors for debugging
- Implement retry logic where appropriate

### 4. Performance
- Don't perform heavy operations in callbacks
- Use threading for long-running tasks
- Cache frequently accessed data

## Advanced Usage

### Custom Logging
```python
import logging
from openctp_sdk.common import setup_logger

# Custom logger configuration
logger = setup_logger(
    name="MyTradingApp",
    level=logging.DEBUG,
    log_file="trading.log"
)
```

### Multiple Gateways
```python
# You can create multiple gateways for different purposes
md_gateway1 = MarketDataGateway("tcp://server1:10131")
md_gateway2 = MarketDataGateway("tcp://server2:10131")

# Each gateway operates independently
md_gateway1.connect()
md_gateway2.connect()
```

### Data Processing Pipeline
```python
import queue
import threading

# Use queues for data processing
data_queue = queue.Queue()

def on_market_data(data):
    data_queue.put(data)

def data_processor():
    while True:
        data = data_queue.get()
        # Process data here
        process_market_data(data)
        data_queue.task_done()

# Start processor thread
threading.Thread(target=data_processor, daemon=True).start()
```

## Troubleshooting

### Common Issues

1. **Import Error**: Make sure OpenCTP is properly installed and the correct version is used.

2. **Connection Timeout**: Check network connectivity and server addresses.

3. **Authentication Failed**: Verify credentials and server configuration.

4. **Order Rejected**: Check account permissions, instrument validity, and market hours.

### Debug Mode

Enable debug logging to see detailed information:

```python
import logging
from openctp_sdk.common import setup_logger

# Enable debug logging
logger = setup_logger("Debug", level=logging.DEBUG)
```

### Network Issues

If experiencing connection issues:
- Check firewall settings
- Verify server addresses and ports
- Test network connectivity
- Check if servers are operational

## Support and Contribution

This SDK is designed to be user-friendly and extensible. Feel free to:
- Report issues and bugs
- Suggest improvements
- Contribute enhancements
- Share usage examples

## License

This SDK is provided under the same license as the OpenCTP project (BSD-3-Clause).

## Disclaimer

This SDK is for educational and development purposes. Users are responsible for:
- Testing thoroughly before production use
- Implementing proper risk management
- Complying with regulatory requirements
- Understanding the risks of automated trading

**Use at your own risk. The authors are not responsible for any financial losses.**