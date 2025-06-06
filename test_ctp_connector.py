import unittest
from unittest.mock import MagicMock, patch, call, ANY
import queue
import time
import logging
import os
import sys

# Ensure ctp_connector can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock the CTP API module before CTPConnector tries to import it
# This is a common pattern for testing code that depends on external libraries.
mock_mdapi = MagicMock()
sys.modules['thostmduserapi'] = mock_mdapi

try:
    from ctp_connector import CTPConnector
except ImportError as e:
    logging.critical(f"Failed to import CTPConnector even with mock: {e}")
    # Define a dummy class if import fails, so test file is syntactically valid
    class CTPConnector:
        def __init__(self, md_front, broker_id, user_id, password, data_q, cmd_q, flow_path_root="."): pass
        def connect(self): pass
        def stop(self): pass
        def login(self): pass
        # Add other methods that might be called if tests run partially
        def subscribe_market_data(self, instruments): pass
        def unsubscribe_market_data(self, instruments): pass
        # Simulate SPI methods if needed by test structure
        def OnFrontConnected(self): pass
        def OnFrontDisconnected(self, reason: int): pass
        def OnRspUserLogin(self, pRspUserLogin, pRspInfo, nRequestID, bIsLast): pass
        def OnRspSubMarketData(self, pSpecificInstrument, pRspInfo, nRequestID, bIsLast): pass
        def OnRspUnSubMarketData(self, pSpecificInstrument, pRspInfo, nRequestID, bIsLast): pass
        def OnRtnDepthMarketData(self, pDepthMarketData): pass


# Configure logging for tests (can be quieted or made verbose)
# logging.disable(logging.CRITICAL) # Uncomment to disable logging during tests

class TestCTPConnector(unittest.TestCase):

    def setUp(self):
        # Reset mocks for each test to ensure isolation
        global mock_mdapi
        mock_mdapi.reset_mock()

        # Mock the CThostFtdcMdApi instance that CreateFtdcMdApi returns
        self.mock_api_instance = MagicMock()
        mock_mdapi.CThostFtdcMdApi.CreateFtdcMdApi.return_value = self.mock_api_instance

        self.data_queue = queue.Queue()
        self.command_queue = queue.Queue()

        # Patch os.makedirs to avoid actual directory creation during tests
        # unless testing that specific functionality.
        patcher = patch('os.makedirs')
        self.addCleanup(patcher.stop) # Stop patcher after test method
        self.mock_makedirs = patcher.start()

        # Flow path needs to exist or be mockable if CTPConnector tries to use it early
        # The connector now creates it, so mocking os.makedirs is important.
        self.connector = CTPConnector(
            md_front="tcp://testfront:12345",
            broker_id="TESTBROKER",
            user_id="testuser",
            password="testpassword",
            data_queue=self.data_queue,
            command_queue=self.command_queue,
            flow_path_root="./test_flow"
        )
        # Suppress logger output for cleaner test runs, unless debugging a test
        # logging.getLogger('ctp_connector').setLevel(logging.CRITICAL + 1)


    def tearDown(self):
        if self.connector and self.connector.running:
            self.connector.stop()
        # Ensure queues are empty
        while not self.data_queue.empty(): self.data_queue.get_nowait()
        while not self.command_queue.empty(): self.command_queue.get_nowait()


    def test_initialization_and_flow_path_creation(self):
        self.assertIsNotNone(self.connector)
        # Check if flow path creation was attempted (os.makedirs was called)
        expected_flow_path = os.path.join(".", "test_flow", "conn_flow", "md")
        self.mock_makedirs.assert_called_once_with(expected_flow_path)
        self.assertEqual(self.connector.flow_path, expected_flow_path)

    def test_connect_and_api_creation(self):
        self.connector.connect()
        mock_mdapi.CThostFtdcMdApi.CreateFtdcMdApi.assert_called_once_with(self.connector.flow_path)
        self.mock_api_instance.RegisterFront.assert_called_once_with("tcp://testfront:12345")
        self.mock_api_instance.RegisterSpi.assert_called_once_with(self.connector)
        self.mock_api_instance.Init.assert_called_once()
        self.assertTrue(self.connector.running)
        self.assertTrue(self.connector.command_thread.is_alive())
        self.connector.stop() # Clean up

    def test_on_front_connected_triggers_login(self):
        self.connector.connect() # This sets up the api instance
        self.connector.OnFrontConnected() # Simulate callback

        self.assertTrue(self.connector.is_connected)
        self.mock_api_instance.ReqUserLogin.assert_called_once()
        args, _ = self.mock_api_instance.ReqUserLogin.call_args
        login_req_field = args[0]
        self.assertEqual(login_req_field.BrokerID, "TESTBROKER")
        self.assertEqual(login_req_field.UserID, "testuser")
        self.connector.stop()

    def test_on_rsp_user_login_success(self):
        # Simulate being connected and login having been requested
        self.connector.is_connected = True
        self.connector.api = self.mock_api_instance # Ensure API is set

        mock_rsp_user_login = MagicMock()
        mock_rsp_user_login.TradingDay = b"20230101"
        mock_rsp_user_login.UserID = b"testuser"

        mock_rsp_info = MagicMock()
        mock_rsp_info.ErrorID = 0
        mock_rsp_info.ErrorMsg = b""

        self.connector.OnRspUserLogin(mock_rsp_user_login, mock_rsp_info, 1, True)
        self.assertTrue(self.connector.is_logged_in)

    def test_on_rsp_user_login_failure(self):
        self.connector.is_connected = True
        self.connector.api = self.mock_api_instance

        mock_rsp_info = MagicMock()
        mock_rsp_info.ErrorID = 10
        mock_rsp_info.ErrorMsg = b"Login failed message"

        self.connector.OnRspUserLogin(MagicMock(), mock_rsp_info, 1, True)
        self.assertFalse(self.connector.is_logged_in)

    def test_subscribe_market_data_command(self):
        # Simulate connected and logged in state
        self.connector.connect() # Start command processor thread
        self.connector.is_connected = True
        self.connector.is_logged_in = True
        self.connector.api = self.mock_api_instance # Ensure API is set for direct calls if any

        instruments = ["IF2301", "ag2301"]
        self.command_queue.put(("subscribe", instruments))

        time.sleep(0.1) # Give command processor time to act

        # Check if SubscribeMarketData was called on the CTP API mock
        # The call is made with encoded instrument IDs
        encoded_instruments = [s.encode('utf-8') for s in instruments]
        self.mock_api_instance.SubscribeMarketData.assert_called_once_with(encoded_instruments, len(encoded_instruments))
        self.connector.stop()

    def test_unsubscribe_market_data_command(self):
        self.connector.connect()
        self.connector.is_connected = True
        self.connector.is_logged_in = True
        self.connector.api = self.mock_api_instance

        # First subscribe (directly, for test setup, normally via command)
        with self.connector.subscription_lock:
            self.connector.subscribed_instruments.add("IF2301")
            self.connector.subscribed_instruments.add("ag2301")

        instruments_to_unsub = ["IF2301"]
        self.command_queue.put(("unsubscribe", instruments_to_unsub))
        time.sleep(0.1)

        encoded_instruments_unsub = [s.encode('utf-8') for s in instruments_to_unsub]
        self.mock_api_instance.UnSubscribeMarketData.assert_called_once_with(encoded_instruments_unsub, len(encoded_instruments_unsub))
        self.connector.stop()

    def test_on_rsp_sub_market_data_updates_set(self):
        self.connector.api = self.mock_api_instance # Ensure API is set

        mock_specific_instrument = MagicMock()
        mock_specific_instrument.InstrumentID = b"IF2301"

        mock_rsp_info_success = MagicMock()
        mock_rsp_info_success.ErrorID = 0

        self.connector.OnRspSubMarketData(mock_specific_instrument, mock_rsp_info_success, 1, True)
        self.assertIn("IF2301", self.connector.subscribed_instruments)

        mock_rsp_info_fail = MagicMock()
        mock_rsp_info_fail.ErrorID = 1
        mock_rsp_info_fail.ErrorMsg = b"Sub error"
        # If a sub fails, it should not be in the set (or removed if added optimistically)
        # Current logic adds on success, so this call should not add "ag2301"
        mock_specific_instrument.InstrumentID = b"ag2301"
        self.connector.OnRspSubMarketData(mock_specific_instrument, mock_rsp_info_fail, 2, True)
        self.assertNotIn("ag2301", self.connector.subscribed_instruments)


    def test_on_rsp_un_sub_market_data_updates_set(self):
        self.connector.api = self.mock_api_instance
        # Pre-populate for test
        with self.connector.subscription_lock:
            self.connector.subscribed_instruments.add("IF2301")
            self.connector.subscribed_instruments.add("au2301") # This one will fail to unsub

        mock_specific_instrument = MagicMock()
        mock_specific_instrument.InstrumentID = b"IF2301"

        mock_rsp_info_success = MagicMock()
        mock_rsp_info_success.ErrorID = 0

        self.connector.OnRspUnSubMarketData(mock_specific_instrument, mock_rsp_info_success, 1, True)
        self.assertNotIn("IF2301", self.connector.subscribed_instruments)
        self.assertIn("au2301", self.connector.subscribed_instruments) # Still there

        mock_rsp_info_fail = MagicMock()
        mock_rsp_info_fail.ErrorID = 1
        mock_rsp_info_fail.ErrorMsg = b"Unsub error"
        mock_specific_instrument.InstrumentID = b"au2301" # Try to unsub this one, but it fails
        self.connector.OnRspUnSubMarketData(mock_specific_instrument, mock_rsp_info_fail, 2, True)
        self.assertIn("au2301", self.connector.subscribed_instruments) # Still there due to failure

    def test_on_rtn_depth_market_data(self):
        self.connector.api = self.mock_api_instance # Ensure API is set for any internal checks

        mock_market_data = MagicMock()
        mock_market_data.InstrumentID = b"rb2301"
        mock_market_data.LastPrice = 3500.0
        mock_market_data.Volume = 1000
        mock_market_data.UpdateTime = b"10:00:00"
        mock_market_data.UpdateMillisec = 500
        mock_market_data.BidPrice1 = 3499.0
        mock_market_data.BidVolume1 = 10
        mock_market_data.AskPrice1 = 3501.0
        mock_market_data.AskVolume1 = 5
        mock_market_data.OpenInterest = 50000.0
        mock_market_data.TradingDay = b"20230101"
        mock_market_data.ExchangeID = b"SHFE"
        # Initialize other float fields that _safe_float might check
        mock_market_data.OpenPrice = 3450.0
        mock_market_data.HighestPrice = 3550.0
        mock_market_data.LowestPrice = 3400.0
        mock_market_data.ClosePrice = float('inf') # Test safe_float
        mock_market_data.SettlementPrice = 3500.0
        mock_market_data.PreClosePrice = 3480.0
        mock_market_data.PreSettlementPrice = 3480.0
        mock_market_data.PreOpenInterest = 48000.0
        mock_market_data.UpperLimitPrice = 3700.0
        mock_market_data.LowerLimitPrice = 3300.0
        mock_market_data.AveragePrice = 3500.0 # Often not populated
        mock_market_data.ActionDay = b"20230101"


        self.connector.OnRtnDepthMarketData(mock_market_data)

        try:
            output_data = self.data_queue.get(timeout=0.1)
            self.assertEqual(output_data["InstrumentID"], "rb2301")
            self.assertEqual(output_data["LastPrice"], 3500.0)
            self.assertEqual(output_data["Volume"], 1000)
            self.assertEqual(output_data["ClosePrice"], 0.0) # Due to safe_float for inf
        except queue.Empty:
            self.fail("Data queue was empty after OnRtnDepthMarketData.")

    def test_resubscribe_on_login(self):
        self.connector.connect() # Sets up API, starts command thread
        self.connector.is_connected = True # Simulate connected
        # Pre-populate subscribed_instruments as if a previous session existed
        with self.connector.subscription_lock:
            self.connector.subscribed_instruments.add("cu2301")
            self.connector.subscribed_instruments.add("zn2301")

        # Simulate successful login
        mock_rsp_user_login = MagicMock()
        mock_rsp_user_login.TradingDay = b"20230101"
        mock_rsp_user_login.UserID = b"testuser"
        mock_rsp_info = MagicMock()
        mock_rsp_info.ErrorID = 0

        self.connector.OnRspUserLogin(mock_rsp_user_login, mock_rsp_info, 1, True)

        # Check if SubscribeMarketData was called for the resubscribed instruments
        # It should be called twice if _internal_subscribe is called for each, or once with a list
        # Current _resubscribe_instruments calls _internal_subscribe once with a list.
        time.sleep(0.1) # Allow command processor or direct calls to happen if any async part

        expected_calls = [
            call([b"cu2301", b"zn2301"], 2), # Order in set might vary, so check contents
            # call([b"zn2301", b"cu2301"], 2) # Alternative order
        ]
        # Check if any of the expected call patterns match
        # self.mock_api_instance.SubscribeMarketData.assert_has_calls(expected_calls, any_order=True)
        # A simpler check for one call with the right instruments:
        args, kwargs = self.mock_api_instance.SubscribeMarketData.call_args
        self.assertEqual(kwargs, {}) # No kwargs expected
        self.assertEqual(len(args[0]), 2) # List of instruments
        self.assertEqual(args[1], 2) # Count
        self.assertIn(b"cu2301", args[0])
        self.assertIn(b"zn2301", args[0])

        self.connector.stop()


    def test_stop_method(self):
        self.connector.connect() # Starts command thread
        self.assertTrue(self.connector.running)
        self.assertTrue(self.connector.command_thread.is_alive())

        self.connector.stop()
        self.assertFalse(self.connector.running)
        # Give command thread time to process shutdown and exit
        self.connector.command_thread.join(timeout=0.1) # Should be quick
        self.assertFalse(self.connector.command_thread.is_alive())
        # Check if API release was simulated (api set to None)
        self.assertIsNone(self.connector.api)


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    unittest.main()
