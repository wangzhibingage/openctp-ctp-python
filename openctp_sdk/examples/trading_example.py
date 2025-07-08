#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Trading Gateway Example

This example demonstrates how to use the TradingGateway SDK for:
- Connecting and authenticating to trading server
- Placing and canceling orders
- Querying positions and account information
- Handling real-time trading updates

Author: OpenCTP SDK Team
"""

import sys
import time
import signal
from typing import List, Dict, Any

# Add parent directory to path to import SDK
sys.path.insert(0, '../')

from openctp_sdk import TradingGateway, OrderInfo, PositionInfo, AccountInfo
from openctp_sdk.common import Direction, Offset, PriceType, OrderStatus, setup_logger

class TradingExample:
    """Example class demonstrating trading gateway usage"""
    
    def __init__(self):
        """Initialize the example"""
        # Setup logging
        self.logger = setup_logger("TradingExample")
        
        # Configuration - replace with your actual credentials
        self.config = {
            "front_address": "tcp://180.168.146.187:10130",  # SimNow trading server
            "broker_id": "9999",
            "user_id": "000001",
            "password": "888888",
            "app_id": "simnow_client_test",
            "auth_code": "0000000000000000"
        }
        
        # Create gateway
        self.gateway = TradingGateway(
            front_address=self.config["front_address"],
            broker_id=self.config["broker_id"],
            user_id=self.config["user_id"],
            password=self.config["password"],
            app_id=self.config["app_id"],
            auth_code=self.config["auth_code"],
            auto_reconnect=True
        )
        
        # Setup callbacks
        self.gateway.set_order_callback(self.on_order_update)
        self.gateway.set_position_callback(self.on_position_update)
        self.gateway.set_account_callback(self.on_account_update)
        self.gateway.set_connection_callback(self.on_connected)
        self.gateway.set_disconnection_callback(self.on_disconnected)
        self.gateway.set_error_callback(self.on_error)
        
        # Track orders
        self.my_orders: Dict[str, OrderInfo] = {}
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def on_order_update(self, order: OrderInfo) -> None:
        """
        Callback for order updates
        
        Args:
            order: Order information
        """
        order_key = f"{order.order_ref}_{order.front_id}_{order.session_id}"
        self.my_orders[order_key] = order
        
        self.logger.info(
            f"Order Update - {order.instrument_id}: "
            f"Ref={order.order_ref}, "
            f"Status={order.order_status}, "
            f"Direction={order.direction}, "
            f"Price={order.limit_price:.2f}, "
            f"Volume={order.volume_total_original}, "
            f"Traded={order.volume_traded}, "
            f"Remaining={order.volume_total}"
        )
        
        # Handle specific order statuses
        if order.order_status == OrderStatus.ALL_TRADED.value:
            self.logger.info(f"Order {order.order_ref} fully filled!")
        elif order.order_status == OrderStatus.CANCELED.value:
            self.logger.info(f"Order {order.order_ref} canceled")
    
    def on_position_update(self, position: PositionInfo) -> None:
        """
        Callback for position updates
        
        Args:
            position: Position information
        """
        if position.position > 0:  # Only log non-zero positions
            self.logger.info(
                f"Position Update - {position.instrument_id}: "
                f"Direction={position.position_direction}, "
                f"Position={position.position}, "
                f"YdPosition={position.yd_position}, "
                f"TodayPosition={position.today_position}, "
                f"PositionProfit={position.position_profit:.2f}"
            )
    
    def on_account_update(self, account: AccountInfo) -> None:
        """
        Callback for account updates
        
        Args:
            account: Account information
        """
        self.logger.info(
            f"Account Update: "
            f"Balance={account.balance:.2f}, "
            f"Available={account.available:.2f}, "
            f"Margin={account.curr_margin:.2f}, "
            f"PositionProfit={account.position_profit:.2f}, "
            f"CloseProfit={account.close_profit:.2f}"
        )
    
    def on_connected(self) -> None:
        """Callback for connection events"""
        self.logger.info("Connected to trading server")
    
    def on_disconnected(self, reason: int) -> None:
        """
        Callback for disconnection events
        
        Args:
            reason: Disconnection reason code
        """
        self.logger.warning(f"Disconnected from trading server (reason: {reason})")
    
    def on_error(self, message: str, error_code: int) -> None:
        """
        Callback for error events
        
        Args:
            message: Error message
            error_code: Error code
        """
        self.logger.error(f"Error occurred: {message} (Code: {error_code})")
    
    def run(self) -> None:
        """Run the trading example"""
        try:
            self.logger.info("Starting Trading Gateway Example")
            self.logger.info(f"Connecting to: {self.config['front_address']}")
            
            # Connect to server (this includes authentication and login)
            self.gateway.connect(timeout=30.0)
            self.logger.info("Successfully connected and authenticated to trading server")
            
            # Wait a moment for everything to settle
            time.sleep(2)
            
            # Demonstrate various trading operations
            self.demonstrate_queries()
            self.demonstrate_trading()
            
            # Keep running to show real-time updates
            self.logger.info("Trading gateway is running. Press Ctrl+C to exit.")
            while True:
                time.sleep(10)
                self.show_status()
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
    
    def demonstrate_queries(self) -> None:
        """Demonstrate query operations"""
        self.logger.info("=== Demonstrating Query Operations ===")
        
        try:
            # Query account information
            self.logger.info("Querying account information...")
            account = self.gateway.query_account(timeout=10.0)
            self.logger.info(f"Account Balance: {account.balance:.2f}, Available: {account.available:.2f}")
            
            # Query positions
            self.logger.info("Querying positions...")
            positions = self.gateway.query_positions(timeout=10.0)
            self.logger.info(f"Found {len(positions)} positions")
            for pos in positions:
                if pos.position > 0:
                    self.logger.info(f"  {pos.instrument_id}: {pos.position} lots")
            
            # Query orders
            self.logger.info("Querying orders...")
            orders = self.gateway.query_orders(timeout=10.0)
            self.logger.info(f"Found {len(orders)} orders")
            for order in orders[-5:]:  # Show last 5 orders
                self.logger.info(f"  {order.instrument_id}: {order.order_status} - {order.volume_total_original} lots")
            
        except Exception as e:
            self.logger.error(f"Error in queries: {e}")
    
    def demonstrate_trading(self) -> None:
        """Demonstrate trading operations"""
        self.logger.info("=== Demonstrating Trading Operations ===")
        
        # WARNING: This is just an example! 
        # In real trading, you should:
        # 1. Use proper risk management
        # 2. Validate prices and volumes
        # 3. Handle errors appropriately
        # 4. Test thoroughly before using real money
        
        try:
            # Example 1: Place a buy order (modify price to be safe)
            self.logger.info("Example: Placing a buy order (using safe price)")
            
            instrument_id = "au2406"  # Gold
            safe_price = 400.0  # Deliberately low price to avoid accidental fills
            volume = 1
            
            order_ref = self.gateway.place_order(
                instrument_id=instrument_id,
                direction=Direction.BUY,
                offset=Offset.OPEN,
                price=safe_price,
                volume=volume,
                price_type=PriceType.LIMIT_PRICE
            )
            
            self.logger.info(f"Placed buy order with reference: {order_ref}")
            
            # Wait a moment to see order status
            time.sleep(3)
            
            # Example 2: Cancel the order
            self.logger.info(f"Canceling order: {order_ref}")
            self.gateway.cancel_order(order_ref)
            
            # Wait to see cancellation
            time.sleep(3)
            
            # Example 3: Show how to place different types of orders
            self._demonstrate_different_order_types()
            
        except Exception as e:
            self.logger.error(f"Error in trading operations: {e}")
    
    def _demonstrate_different_order_types(self) -> None:
        """Demonstrate different order types"""
        self.logger.info("--- Different Order Types ---")
        
        # Note: These examples use safe prices to avoid accidental fills
        examples = [
            {
                "name": "Buy to open position",
                "instrument": "ag2406",
                "direction": Direction.BUY,
                "offset": Offset.OPEN,
                "price": 3000.0,  # Silver - safe low price
                "volume": 1
            },
            {
                "name": "Sell to close position", 
                "instrument": "cu2406",
                "direction": Direction.SELL,
                "offset": Offset.CLOSE,
                "price": 50000.0,  # Copper - safe high price
                "volume": 1
            }
        ]
        
        placed_orders = []
        
        for example in examples:
            try:
                self.logger.info(f"Placing order: {example['name']}")
                
                order_ref = self.gateway.place_order(
                    instrument_id=example["instrument"],
                    direction=example["direction"],
                    offset=example["offset"],
                    price=example["price"],
                    volume=example["volume"]
                )
                
                placed_orders.append(order_ref)
                self.logger.info(f"Order placed: {order_ref}")
                time.sleep(1)  # Brief pause between orders
                
            except Exception as e:
                self.logger.error(f"Failed to place {example['name']}: {e}")
        
        # Cancel all placed orders after a moment
        time.sleep(5)
        for order_ref in placed_orders:
            try:
                self.logger.info(f"Canceling order: {order_ref}")
                self.gateway.cancel_order(order_ref)
                time.sleep(1)
            except Exception as e:
                self.logger.error(f"Failed to cancel {order_ref}: {e}")
    
    def show_status(self) -> None:
        """Show current status"""
        try:
            status = (
                f"Status: Connected={self.gateway.is_connected()}, "
                f"Authenticated={self.gateway.is_authenticated()}, "
                f"LoggedIn={self.gateway.is_logged_in()}, "
                f"ReadyForTrading={self.gateway.is_ready_for_trading()}"
            )
            self.logger.info(status)
            
            # Show cached data
            orders = self.gateway.get_cached_orders()
            positions = self.gateway.get_cached_positions()
            account = self.gateway.get_cached_account()
            
            self.logger.info(f"Cached data: {len(orders)} orders, {len(positions)} positions, "
                           f"Account available: {account.available:.2f}" if account else "No account data")
            
        except Exception as e:
            self.logger.error(f"Error showing status: {e}")
    
    def cleanup(self) -> None:
        """Clean up resources"""
        try:
            self.logger.info("Cleaning up...")
            
            if self.gateway:
                # Optionally cancel all pending orders before disconnect
                # (In production, you might want to keep orders active)
                
                self.gateway.disconnect()
                self.logger.info("Disconnected from trading server")
            
            self.logger.info(f"Total orders tracked: {len(self.my_orders)}")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle system signals"""
        self.logger.info(f"Received signal {signum}")
        sys.exit(0)

def demonstrate_basic_usage():
    """Demonstrate basic trading gateway usage"""
    print("=== Trading Gateway Basic Usage Demo ===")
    
    # Note: Replace with your actual credentials
    gateway = TradingGateway(
        front_address="tcp://180.168.146.187:10130",
        broker_id="9999",
        user_id="000001", 
        password="888888",
        app_id="simnow_client_test",
        auth_code="0000000000000000"
    )
    
    try:
        # Connect (includes authentication and login)
        print("Connecting...")
        gateway.connect(timeout=30.0)
        print("Connected successfully!")
        
        # Query account
        print("Querying account...")
        account = gateway.query_account()
        print(f"Account balance: {account.balance:.2f}")
        
        # Query positions
        print("Querying positions...")
        positions = gateway.query_positions()
        print(f"Number of positions: {len(positions)}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        gateway.disconnect()
        print("Basic demo completed")

def demonstrate_order_management():
    """Demonstrate order management features"""
    print("\n=== Order Management Demo ===")
    
    # This demo shows order management without actually trading
    print("Note: This demo uses safe prices to avoid accidental trades")
    
    gateway = TradingGateway(
        front_address="tcp://180.168.146.187:10130", 
        broker_id="9999",
        user_id="000001",
        password="888888",
        app_id="simnow_client_test", 
        auth_code="0000000000000000"
    )
    
    def on_order_update(order: OrderInfo):
        print(f"Order {order.order_ref}: {order.order_status}")
    
    gateway.set_order_callback(on_order_update)
    
    try:
        gateway.connect()
        
        # Place and immediately cancel an order
        print("Placing order...")
        order_ref = gateway.place_order(
            instrument_id="au2406",
            direction=Direction.BUY,
            offset=Offset.OPEN,
            price=400.0,  # Safe low price
            volume=1
        )
        
        print(f"Order placed: {order_ref}")
        time.sleep(2)
        
        print("Canceling order...")
        gateway.cancel_order(order_ref)
        time.sleep(2)
        
    finally:
        gateway.disconnect()
        print("Order management demo completed")

if __name__ == "__main__":
    """Main entry point"""
    
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # Run quick demos
        demonstrate_basic_usage()
        demonstrate_order_management()
    else:
        # Run full example
        print("WARNING: This example will connect to a trading server.")
        print("Make sure you understand the code and use appropriate credentials.")
        print("Press Ctrl+C to exit at any time.")
        print()
        
        example = TradingExample()
        example.run()