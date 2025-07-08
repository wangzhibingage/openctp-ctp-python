#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OpenCTP SDK Setup Validator

This utility helps validate that your OpenCTP SDK setup is correct
and can connect to the CTP servers.

Run this script to check:
- SDK imports
- CTP library availability  
- Server connectivity
- Authentication

Author: OpenCTP SDK Team
"""

import sys
import time
import platform
import os
from typing import Dict, Any, Optional

# Add paths for SDK import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

def print_header(title: str):
    """Print a formatted header"""
    print(f"\n{'='*60}")
    print(f" {title}")
    print(f"{'='*60}")

def print_status(item: str, status: bool, details: str = ""):
    """Print status with checkmark or X"""
    symbol = "✓" if status else "✗"
    status_text = "PASS" if status else "FAIL"
    print(f"{symbol} {item:<40} [{status_text}]")
    if details:
        print(f"  {details}")

def check_python_version() -> bool:
    """Check Python version compatibility"""
    version = sys.version_info
    is_compatible = version >= (3, 7)
    details = f"Python {version.major}.{version.minor}.{version.micro}"
    if not is_compatible:
        details += " (Requires Python 3.7+)"
    print_status("Python Version", is_compatible, details)
    return is_compatible

def check_platform() -> bool:
    """Check platform compatibility"""
    system = platform.system()
    machine = platform.machine()
    
    supported_platforms = {
        "Windows": ["AMD64", "x86"],
        "Linux": ["x86_64"],
        "Darwin": ["x86_64", "arm64"]  # macOS
    }
    
    is_supported = (system in supported_platforms and 
                   machine in supported_platforms[system])
    
    details = f"{system} {machine}"
    if not is_supported:
        details += " (May not be supported)"
    
    print_status("Platform", is_supported, details)
    return is_supported

def check_sdk_imports() -> bool:
    """Check if SDK can be imported"""
    try:
        # Add current directory and parent to path
        import os
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        
        from openctp_sdk.common import Direction, MarketData, setup_logger
        print_status("SDK Common Imports", True, "Basic SDK components available")
        return True
    except ImportError as e:
        print_status("SDK Common Imports", False, f"Import error: {e}")
        return False

def check_ctp_libraries() -> bool:
    """Check if CTP libraries are available"""
    ctp_available = False
    
    try:
        # Try to add CTP path
        from openctp_sdk.common.utils import add_ctp_library_path
        add_ctp_library_path()
        
        # Try importing market data API
        try:
            import thostmduserapi
            print_status("Market Data API", True, "thostmduserapi available")
            ctp_available = True
        except ImportError as e:
            print_status("Market Data API", False, f"Import error: {e}")
        
        # Try importing trading API
        try:
            import thosttraderapi
            print_status("Trading API", True, "thosttraderapi available")
            ctp_available = True
        except ImportError as e:
            print_status("Trading API", False, f"Import error: {e}")
            
        # Try openctp_ctp import
        try:
            from openctp_ctp import tdapi
            print_status("OpenCTP Trading API", True, "openctp_ctp.tdapi available")
            ctp_available = True
        except ImportError as e:
            print_status("OpenCTP Trading API", False, f"Import error: {e}")
            
    except Exception as e:
        print_status("CTP Library Path", False, f"Error: {e}")
    
    if not ctp_available:
        print("  Suggestion: Install OpenCTP with:")
        print("  pip install openctp-ctp==6.7.2.* -i https://pypi.tuna.tsinghua.edu.cn/simple")
    
    return ctp_available

def check_gateway_imports() -> bool:
    """Check if gateway classes can be imported"""
    try:
        from openctp_sdk import MarketDataGateway, TradingGateway
        if MarketDataGateway is None or TradingGateway is None:
            print_status("Gateway Classes", False, "Gateways are None (CTP libraries missing)")
            return False
        else:
            print_status("Gateway Classes", True, "MarketDataGateway and TradingGateway available")
            return True
    except ImportError as e:
        print_status("Gateway Classes", False, f"Import error: {e}")
        return False

def test_market_data_connection(server: str = "tcp://180.168.146.187:10131") -> bool:
    """Test market data connection"""
    try:
        from openctp_sdk import MarketDataGateway
        
        if MarketDataGateway is None:
            print_status("Market Data Connection", False, "MarketDataGateway not available")
            return False
        
        print(f"  Testing connection to {server}...")
        
        gateway = MarketDataGateway(server)
        
        # Quick connection test
        try:
            gateway.connect(timeout=5.0)
            if gateway.is_connected():
                print_status("Market Data Connection", True, f"Connected to {server}")
                gateway.disconnect()
                return True
            else:
                print_status("Market Data Connection", False, "Failed to connect within timeout")
                return False
        except Exception as e:
            print_status("Market Data Connection", False, f"Connection error: {e}")
            return False
        finally:
            try:
                gateway.disconnect()
            except:
                pass
                
    except Exception as e:
        print_status("Market Data Connection", False, f"Setup error: {e}")
        return False

def test_trading_connection(config: Dict[str, Any]) -> bool:
    """Test trading connection with provided credentials"""
    try:
        from openctp_sdk import TradingGateway
        
        if TradingGateway is None:
            print_status("Trading Connection", False, "TradingGateway not available")
            return False
        
        print(f"  Testing connection to {config['front_address']}...")
        
        gateway = TradingGateway(**config)
        
        # Quick connection test
        try:
            gateway.connect(timeout=10.0)
            if gateway.is_ready_for_trading():
                print_status("Trading Connection", True, "Connected and authenticated")
                gateway.disconnect()
                return True
            else:
                status = (f"Connected={gateway.is_connected()}, "
                         f"Authenticated={gateway.is_authenticated()}, "
                         f"LoggedIn={gateway.is_logged_in()}")
                print_status("Trading Connection", False, f"Not ready for trading: {status}")
                return False
        except Exception as e:
            print_status("Trading Connection", False, f"Connection error: {e}")
            return False
        finally:
            try:
                gateway.disconnect()
            except:
                pass
                
    except Exception as e:
        print_status("Trading Connection", False, f"Setup error: {e}")
        return False

def load_test_config() -> Optional[Dict[str, Any]]:
    """Load test configuration"""
    try:
        from openctp_sdk.common import load_config
        config = load_config("examples/config.json")
        return config.get("trading", {})
    except:
        # Return SimNow default config
        return {
            "front_address": "tcp://180.168.146.187:10130",
            "broker_id": "9999",
            "user_id": "000001",  # User should replace this
            "password": "888888",  # User should replace this
            "app_id": "simnow_client_test",
            "auth_code": "0000000000000000"
        }

def main():
    """Main validation function"""
    print_header("OpenCTP SDK Setup Validator")
    print("This tool validates your OpenCTP SDK installation and setup.")
    print("It checks imports, CTP libraries, and server connectivity.")
    
    # Basic checks
    print_header("Basic Environment Checks")
    python_ok = check_python_version()
    platform_ok = check_platform()
    
    # SDK checks
    print_header("SDK Import Checks")
    sdk_imports_ok = check_sdk_imports()
    ctp_libs_ok = check_ctp_libraries()
    gateways_ok = check_gateway_imports()
    
    # Connection tests
    print_header("Connectivity Tests")
    
    # Market data test (no credentials needed)
    md_connection_ok = test_market_data_connection()
    
    # Trading test (needs credentials)
    td_connection_ok = False
    test_config = load_test_config()
    
    if test_config and test_config.get("user_id") != "000001":
        # User has configured credentials
        td_connection_ok = test_trading_connection(test_config)
    else:
        print_status("Trading Connection", False, 
                    "No valid credentials configured (update examples/config.json)")
    
    # Summary
    print_header("Validation Summary")
    
    total_checks = 7
    passed_checks = sum([
        python_ok, platform_ok, sdk_imports_ok, 
        ctp_libs_ok, gateways_ok, md_connection_ok, td_connection_ok
    ])
    
    print(f"Passed: {passed_checks}/{total_checks} checks")
    
    if passed_checks >= 5:  # Core functionality works
        print("\n✓ Your OpenCTP SDK setup looks good!")
        if not td_connection_ok:
            print("  Note: Configure trading credentials in examples/config.json to test trading connection")
    else:
        print(f"\n✗ Setup issues detected. Please address the failed checks above.")
        
        if not ctp_libs_ok:
            print("\nQuick fix for CTP libraries:")
            print("pip install openctp-ctp==6.7.2.* -i https://pypi.tuna.tsinghua.edu.cn/simple")
    
    print_header("Next Steps")
    print("1. Check examples/ directory for usage examples")
    print("2. Read README.md for detailed documentation")  
    print("3. Configure examples/config.json with your credentials")
    print("4. Run examples to test functionality")

if __name__ == "__main__":
    main()