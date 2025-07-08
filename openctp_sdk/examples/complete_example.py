#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Complete OpenCTP SDK Example

This example demonstrates how to use both MarketDataGateway and TradingGateway
together in a complete trading application.

Author: OpenCTP SDK Team
"""

import sys
import time
import json
import threading
from typing import Dict, List

# Add parent directory to path to import SDK
sys.path.insert(0, '../')

from openctp_sdk import MarketDataGateway, TradingGateway, MarketData, OrderInfo
from openctp_sdk.common import Direction, Offset, PriceType, setup_logger, load_config

class TradingBot:
    """
    Example trading bot using both market data and trading gateways
    
    This is a simple example that demonstrates:
    - Receiving market data
    - Making trading decisions
    - Placing and managing orders
    - Risk management
    
    WARNING: This is for demonstration purposes only!
    Do not use in production without proper testing and risk management.
    """
    
    def __init__(self, config_path: str = "config.json"):
        """Initialize the trading bot"""
        # Load configuration
        self.config = load_config(config_path)
        
        # Setup logging
        self.logger = setup_logger("TradingBot")
        
        # Initialize gateways
        self.market_gateway = MarketDataGateway(
            front_address=self.config["market_data"]["front_address"],
            user_id=self.config["market_data"]["user_id"],
            password=self.config["market_data"]["password"],
            broker_id=self.config["market_data"]["broker_id"],
            auto_reconnect=self.config["market_data"]["auto_reconnect"]
        )
        
        self.trading_gateway = TradingGateway(
            front_address=self.config["trading"]["front_address"],
            broker_id=self.config["trading"]["broker_id"],
            user_id=self.config["trading"]["user_id"],
            password=self.config["trading"]["password"],
            app_id=self.config["trading"]["app_id"],
            auth_code=self.config["trading"]["auth_code"],
            auto_reconnect=self.config["trading"]["auto_reconnect"]
        )
        
        # Setup callbacks
        self.market_gateway.set_market_data_callback(self.on_market_data)
        self.market_gateway.set_connection_callback(self.on_market_connected)
        self.market_gateway.set_error_callback(self.on_market_error)
        
        self.trading_gateway.set_order_callback(self.on_order_update)
        self.trading_gateway.set_connection_callback(self.on_trading_connected)
        self.trading_gateway.set_error_callback(self.on_trading_error)
        
        # Data storage
        self.market_data: Dict[str, MarketData] = {}
        self.active_orders: Dict[str, OrderInfo] = {}
        
        # Trading parameters (for demo)
        self.target_instrument = "au2406"
        self.max_position = 2
        self.price_threshold = 0.1  # Price change threshold for trading signal
        
        # State
        self.market_connected = False
        self.trading_connected = False
        self.running = False
    
    def on_market_data(self, data: MarketData) -> None:
        """Handle market data updates"""
        self.market_data[data.instrument_id] = data
        
        # Simple trading logic (for demonstration)
        if (data.instrument_id == self.target_instrument and 
            self.trading_connected and 
            self.running):
            self.check_trading_signals(data)
    
    def on_market_connected(self) -> None:
        """Handle market data connection"""
        self.logger.info("Market data connected")
        self.market_connected = True
        
        # Subscribe to instruments
        instruments = self.config["market_data"]["instruments"]
        self.market_gateway.subscribe(instruments)
    
    def on_market_error(self, message: str, error_code: int) -> None:
        """Handle market data errors"""
        self.logger.error(f"Market data error: {message} (Code: {error_code})")
    
    def on_order_update(self, order: OrderInfo) -> None:
        """Handle order updates"""
        order_key = f"{order.order_ref}_{order.front_id}_{order.session_id}"
        self.active_orders[order_key] = order
        
        self.logger.info(f"Order update: {order.instrument_id} - {order.order_status}")
    
    def on_trading_connected(self) -> None:
        """Handle trading connection"""
        self.logger.info("Trading connected")
        self.trading_connected = True
    
    def on_trading_error(self, message: str, error_code: int) -> None:
        """Handle trading errors"""
        self.logger.error(f"Trading error: {message} (Code: {error_code})")
    
    def check_trading_signals(self, data: MarketData) -> None:
        """
        Check for trading signals (simplified example)
        
        This is a very basic example - in real trading you would use
        proper technical analysis, risk management, etc.
        """
        try:
            # Get current position
            positions = self.trading_gateway.get_cached_positions()
            current_position = 0
            
            for pos_key, pos in positions.items():
                if pos.instrument_id == self.target_instrument:
                    if pos.position_direction == "2":  # Long position
                        current_position += pos.position
                    elif pos.position_direction == "3":  # Short position
                        current_position -= pos.position
            
            # Simple signal: buy if price drops significantly, sell if it rises
            # (This is just for demonstration - not a real trading strategy!)
            
            if (current_position < self.max_position and 
                data.last_price < data.pre_settlement_price * (1 - self.price_threshold)):
                
                self.logger.info(f"Buy signal for {data.instrument_id} at {data.last_price}")
                # Note: Using safe price for demo
                self.place_safe_order(data.instrument_id, Direction.BUY, Offset.OPEN)
                
            elif (current_position > -self.max_position and 
                  data.last_price > data.pre_settlement_price * (1 + self.price_threshold)):
                
                self.logger.info(f"Sell signal for {data.instrument_id} at {data.last_price}")
                # Note: Using safe price for demo
                self.place_safe_order(data.instrument_id, Direction.SELL, Offset.OPEN)
                
        except Exception as e:
            self.logger.error(f"Error in trading signal check: {e}")
    
    def place_safe_order(self, instrument_id: str, direction: Direction, offset: Offset) -> None:
        """
        Place an order with safe price (for demonstration)
        
        In real trading, you would use market prices, proper risk management, etc.
        """
        try:
            # Use very safe prices to avoid accidental fills in demo
            if direction == Direction.BUY:
                price = 400.0  # Very low price for gold
            else:
                price = 600.0  # Still safe but higher
            
            order_ref = self.trading_gateway.place_order(
                instrument_id=instrument_id,
                direction=direction,
                offset=offset,
                price=price,
                volume=1,
                price_type=PriceType.LIMIT_PRICE
            )
            
            self.logger.info(f"Placed safe order: {order_ref}")
            
            # Cancel the order after a few seconds (for demo purposes)
            def cancel_later():
                time.sleep(5)
                try:
                    self.trading_gateway.cancel_order(order_ref)
                    self.logger.info(f"Canceled demo order: {order_ref}")
                except Exception as e:
                    self.logger.error(f"Failed to cancel order: {e}")
            
            threading.Thread(target=cancel_later, daemon=True).start()
            
        except Exception as e:
            self.logger.error(f"Failed to place order: {e}")
    
    def start(self) -> None:
        """Start the trading bot"""
        try:
            self.logger.info("Starting trading bot...")
            
            # Connect to market data first
            self.logger.info("Connecting to market data...")
            self.market_gateway.connect(timeout=10.0)
            
            # Connect to trading
            self.logger.info("Connecting to trading...")
            self.trading_gateway.connect(timeout=30.0)
            
            # Start running
            self.running = True
            self.logger.info("Trading bot started successfully")
            
        except Exception as e:
            self.logger.error(f"Failed to start trading bot: {e}")
            raise
    
    def stop(self) -> None:
        """Stop the trading bot"""
        try:
            self.logger.info("Stopping trading bot...")
            self.running = False
            
            # Cancel all pending orders (optional)
            for order_key, order in self.active_orders.items():
                if order.order_status in ["3", "1"]:  # Pending orders
                    try:
                        self.trading_gateway.cancel_order(order.order_ref)
                        self.logger.info(f"Canceled order: {order.order_ref}")
                    except Exception as e:
                        self.logger.warning(f"Failed to cancel order {order.order_ref}: {e}")
            
            # Disconnect gateways
            self.market_gateway.disconnect()
            self.trading_gateway.disconnect()
            
            self.logger.info("Trading bot stopped")
            
        except Exception as e:
            self.logger.error(f"Error stopping trading bot: {e}")
    
    def show_status(self) -> None:
        """Show current status"""
        try:
            # Market data status
            market_status = (
                f"Market: Connected={self.market_gateway.is_connected()}, "
                f"Subscribed={len(self.market_gateway.get_subscribed_instruments())}"
            )
            
            # Trading status
            trading_status = (
                f"Trading: Connected={self.trading_gateway.is_connected()}, "
                f"Ready={self.trading_gateway.is_ready_for_trading()}"
            )
            
            # Data status
            data_status = f"Market data: {len(self.market_data)} instruments"
            order_status = f"Active orders: {len(self.active_orders)}"
            
            self.logger.info(f"Status - {market_status}, {trading_status}, {data_status}, {order_status}")
            
            # Show latest prices
            if self.market_data:
                for instrument_id, data in list(self.market_data.items())[:3]:  # Show first 3
                    self.logger.info(f"  {instrument_id}: {data.last_price:.2f}")
            
        except Exception as e:
            self.logger.error(f"Error showing status: {e}")

def main():
    """Main function"""
    import signal
    
    # Create trading bot
    try:
        bot = TradingBot()
    except Exception as e:
        print(f"Failed to create trading bot: {e}")
        print("Please check your configuration in config.json")
        return
    
    # Setup signal handler
    def signal_handler(signum, frame):
        print(f"Received signal {signum}")
        bot.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    try:
        # Start the bot
        bot.start()
        
        # Main loop
        print("Trading bot is running. Press Ctrl+C to stop.")
        while True:
            time.sleep(30)  # Show status every 30 seconds
            bot.show_status()
            
    except KeyboardInterrupt:
        print("Received keyboard interrupt")
    except Exception as e:
        print(f"Error in main loop: {e}")
    finally:
        bot.stop()

if __name__ == "__main__":
    print("=== Complete OpenCTP SDK Example ===")
    print()
    print("This example demonstrates a simple trading bot using both")
    print("market data and trading gateways.")
    print()
    print("WARNING: This is for demonstration purposes only!")
    print("Do not use in production without proper testing.")
    print()
    print("Make sure to configure config.json with your credentials.")
    print()
    
    main()