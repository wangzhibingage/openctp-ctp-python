#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Market Data Gateway Example

This example demonstrates how to use the MarketDataGateway SDK for:
- Connecting to market data server
- Subscribing to instrument data
- Handling real-time market data updates
- Error handling and reconnection

Author: OpenCTP SDK Team
"""

import sys
import time
import signal
from typing import List

# Add parent directory to path to import SDK
sys.path.insert(0, '../')

from openctp_sdk import MarketDataGateway, MarketData
from openctp_sdk.common import setup_logger

class MarketDataExample:
    """Example class demonstrating market data gateway usage"""
    
    def __init__(self):
        """Initialize the example"""
        # Setup logging
        self.logger = setup_logger("MarketDataExample")
        
        # Configuration - replace with your actual server details
        self.config = {
            "front_address": "tcp://180.168.146.187:10131",  # SimNow market data server
            "user_id": "",      # Optional for market data
            "password": "",     # Optional for market data
            "broker_id": "",    # Optional for market data
            "instruments": ["au2406", "ag2406", "cu2406", "rb2406"]  # Instruments to subscribe
        }
        
        # Create gateway
        self.gateway = MarketDataGateway(
            front_address=self.config["front_address"],
            user_id=self.config["user_id"],
            password=self.config["password"],
            broker_id=self.config["broker_id"],
            auto_reconnect=True
        )
        
        # Setup callbacks
        self.gateway.set_market_data_callback(self.on_market_data)
        self.gateway.set_connection_callback(self.on_connected)
        self.gateway.set_disconnection_callback(self.on_disconnected)
        self.gateway.set_error_callback(self.on_error)
        
        # Track statistics
        self.data_count = 0
        self.start_time = time.time()
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def on_market_data(self, data: MarketData) -> None:
        """
        Callback for market data updates
        
        Args:
            data: Market data structure
        """
        self.data_count += 1
        
        # Print market data (you can customize this based on your needs)
        self.logger.info(
            f"Market Data - {data.instrument_id}: "
            f"Price={data.last_price:.2f}, "
            f"Volume={data.volume}, "
            f"Bid={data.bid_price1:.2f}({data.bid_volume1}), "
            f"Ask={data.ask_price1:.2f}({data.ask_volume1}), "
            f"Time={data.update_time}.{data.update_millisec:03d}"
        )
        
        # Print statistics every 100 updates
        if self.data_count % 100 == 0:
            elapsed = time.time() - self.start_time
            rate = self.data_count / elapsed if elapsed > 0 else 0
            self.logger.info(f"Statistics: {self.data_count} updates, {rate:.1f} updates/sec")
    
    def on_connected(self) -> None:
        """Callback for connection events"""
        self.logger.info("Connected to market data server")
        
        # Subscribe to instruments after connection
        try:
            self.logger.info(f"Subscribing to instruments: {self.config['instruments']}")
            self.gateway.subscribe(self.config["instruments"])
        except Exception as e:
            self.logger.error(f"Failed to subscribe to instruments: {e}")
    
    def on_disconnected(self, reason: int) -> None:
        """
        Callback for disconnection events
        
        Args:
            reason: Disconnection reason code
        """
        self.logger.warning(f"Disconnected from market data server (reason: {reason})")
    
    def on_error(self, message: str, error_code: int) -> None:
        """
        Callback for error events
        
        Args:
            message: Error message
            error_code: Error code
        """
        self.logger.error(f"Error occurred: {message} (Code: {error_code})")
    
    def run(self) -> None:
        """Run the market data example"""
        try:
            self.logger.info("Starting Market Data Gateway Example")
            self.logger.info(f"Connecting to: {self.config['front_address']}")
            
            # Connect to server
            self.gateway.connect(timeout=10.0)
            self.logger.info("Successfully connected to market data server")
            
            # Keep running until interrupted
            self.logger.info("Market data gateway is running. Press Ctrl+C to exit.")
            while True:
                time.sleep(1)
                
                # Print connection status every 60 seconds
                if int(time.time()) % 60 == 0:
                    subscribed = self.gateway.get_subscribed_instruments()
                    self.logger.info(f"Status: Connected={self.gateway.is_connected()}, "
                                   f"LoggedIn={self.gateway.is_logged_in()}, "
                                   f"Subscribed={len(subscribed)} instruments")
                
        except KeyboardInterrupt:
            self.logger.info("Received interrupt signal")
        except Exception as e:
            self.logger.error(f"Error in main loop: {e}")
        finally:
            self.cleanup()
    
    def cleanup(self) -> None:
        """Clean up resources"""
        try:
            self.logger.info("Cleaning up...")
            
            if self.gateway:
                # Unsubscribe from all instruments
                subscribed = self.gateway.get_subscribed_instruments()
                if subscribed:
                    self.logger.info(f"Unsubscribing from {len(subscribed)} instruments")
                    self.gateway.unsubscribe(subscribed)
                
                # Disconnect
                self.gateway.disconnect()
                self.logger.info("Disconnected from market data server")
            
            # Print final statistics
            elapsed = time.time() - self.start_time
            rate = self.data_count / elapsed if elapsed > 0 else 0
            self.logger.info(f"Final Statistics: {self.data_count} updates received, "
                           f"{rate:.1f} updates/sec average")
            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")
    
    def signal_handler(self, signum, frame):
        """Handle system signals"""
        self.logger.info(f"Received signal {signum}")
        sys.exit(0)

def demonstrate_basic_usage():
    """Demonstrate basic market data gateway usage"""
    print("=== Market Data Gateway Basic Usage Demo ===")
    
    # Create gateway with minimal configuration
    gateway = MarketDataGateway("tcp://180.168.146.187:10131")
    
    # Simple callback
    def print_data(data: MarketData):
        print(f"{data.instrument_id}: {data.last_price}")
    
    gateway.set_market_data_callback(print_data)
    
    try:
        # Connect and subscribe
        gateway.connect()
        gateway.subscribe(["au2406"])
        
        # Run for 10 seconds
        print("Receiving market data for 10 seconds...")
        time.sleep(10)
        
    finally:
        gateway.disconnect()
        print("Basic demo completed")

def demonstrate_advanced_features():
    """Demonstrate advanced features"""
    print("\n=== Advanced Features Demo ===")
    
    gateway = MarketDataGateway(
        front_address="tcp://180.168.146.187:10131",
        auto_reconnect=True
    )
    
    # Advanced callback with data processing
    def process_data(data: MarketData):
        # Calculate spread
        if data.bid_price1 > 0 and data.ask_price1 > 0:
            spread = data.ask_price1 - data.bid_price1
            spread_pct = (spread / data.last_price) * 100 if data.last_price > 0 else 0
            
            print(f"{data.instrument_id}: Price={data.last_price:.2f}, "
                  f"Spread={spread:.4f} ({spread_pct:.3f}%), "
                  f"Volume={data.volume}")
    
    gateway.set_market_data_callback(process_data)
    
    # Connection status tracking
    def on_connected():
        print("Connected! Subscribing to multiple instruments...")
        gateway.subscribe(["au2406", "ag2406", "cu2406"])
    
    def on_disconnected(reason):
        print(f"Disconnected (reason: {reason}). Auto-reconnect is enabled.")
    
    gateway.set_connection_callback(on_connected)
    gateway.set_disconnection_callback(on_disconnected)
    
    try:
        gateway.connect()
        
        # Dynamic subscription management
        time.sleep(5)
        print("Adding more instruments...")
        gateway.subscribe(["rb2406", "hc2406"])
        
        time.sleep(5)
        print("Removing some instruments...")
        gateway.unsubscribe(["cu2406", "hc2406"])
        
        time.sleep(5)
        
    finally:
        gateway.disconnect()
        print("Advanced demo completed")

if __name__ == "__main__":
    """Main entry point"""
    
    if len(sys.argv) > 1 and sys.argv[1] == "--demo":
        # Run quick demos
        demonstrate_basic_usage()
        demonstrate_advanced_features()
    else:
        # Run full example
        example = MarketDataExample()
        example.run()