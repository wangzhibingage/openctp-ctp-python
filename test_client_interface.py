import unittest
from unittest.mock import MagicMock, patch, AsyncMock, call, ANY
import queue
import asyncio
import json
import logging
import sys
import os
import threading # For parts of ClientInterface that use it

# Ensure client_interface can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Mock websockets and other modules if they are not available in the test environment
# or if we want to control their behavior precisely.
# Since websockets is a core dependency, it should ideally be installed.
# For asyncio parts, we'll use AsyncMock.
try:
    import websockets
except ImportError:
    sys.modules['websockets'] = MagicMock()
    sys.modules['websockets.exceptions'] = MagicMock() # Mock exceptions submodule if needed

try:
    from client_interface import ClientInterface
except ImportError as e:
    logging.critical(f"Failed to import ClientInterface: {e}")
    # Dummy class for syntax validity if import fails
    class ClientInterface:
        def __init__(self, host, port, data_input_q, ctp_cmd_q): pass
        def start(self): pass
        def stop(self): pass


# Suppress logging for cleaner test output if not debugging tests
# logging.disable(logging.CRITICAL)

class TestClientInterface(unittest.IsolatedAsyncioTestCase): # Use IsolatedAsyncioTestCase for async tests

    async def asyncSetUp(self):
        self.data_input_queue = queue.Queue()
        self.ctp_command_queue = queue.Queue()
        self.interface = ClientInterface(
            host="localhost",
            port=8765,
            data_input_queue=self.data_input_queue,
            ctp_command_queue=self.ctp_command_queue
        )
        # It's tricky to fully mock websockets.serve, so we'll mostly test handlers and internal logic.
        # For start/stop, we might patch the server starting part.
        # Suppress logs from the module under test unless needed for debugging
        # logging.getLogger('client_interface').setLevel(logging.CRITICAL + 1)


    async def asyncTearDown(self):
        if self.interface and self.interface.running:
            # Ensure proper cleanup for async server
            self.interface.stop()
            # Give a moment for threads/loops to close if stop is not fully synchronous
            if self.interface.server_thread and self.interface.server_thread.is_alive():
                 self.interface.server_thread.join(0.1) # Short timeout
            if self.interface.data_broadcaster_thread and self.interface.data_broadcaster_thread.is_alive():
                self.interface.data_broadcaster_thread.join(0.1)

        while not self.data_input_queue.empty(): self.data_input_queue.get_nowait()
        while not self.ctp_command_queue.empty(): self.ctp_command_queue.get_nowait()


    def test_initialization(self):
        self.assertIsNotNone(self.interface)
        self.assertEqual(self.interface.host, "localhost")
        self.assertEqual(self.interface.port, 8765)
        self.assertFalse(self.interface.running)

    @patch('websockets.serve', new_callable=AsyncMock) # Mock the serve function
    async def test_start_and_stop_server_logic(self, mock_serve):
        # This test focuses on the threading and async loop management part of start/stop,
        # not the full WebSocket server behavior.

        # Mock the server object returned by websockets.serve
        mock_ws_server_instance = AsyncMock()
        mock_ws_server_instance.close = MagicMock() # Sync mock for close
        mock_ws_server_instance.wait_closed = AsyncMock()
        mock_serve.return_value = mock_ws_server_instance

        self.interface.start()
        self.assertTrue(self.interface.running)
        self.assertIsNotNone(self.interface.server_thread)
        self.assertTrue(self.interface.server_thread.is_alive())

        # Give a moment for the server thread and its internal loop to start
        await asyncio.sleep(0.1)
        self.assertIsNotNone(self.interface.server_loop, "Server event loop was not captured.")
        self.assertTrue(self.interface.data_broadcaster_thread.is_alive())

        mock_serve.assert_called_once() # Check if websockets.serve was called

        self.interface.stop()
        # Stop should join threads. Allow time for this.
        # The actual join happens in the test's asyncTearDown or here explicitly for test clarity.
        if self.interface.server_thread and self.interface.server_thread.is_alive():
            self.interface.server_thread.join(timeout=1.0) # Wait for server thread
        if self.interface.data_broadcaster_thread and self.interface.data_broadcaster_thread.is_alive():
            self.interface.data_broadcaster_thread.join(timeout=1.0)

        self.assertFalse(self.interface.running, "Interface should not be running after stop.")
        self.assertFalse(self.interface.server_thread.is_alive(), "Server thread should be stopped.")
        self.assertFalse(self.interface.data_broadcaster_thread.is_alive(), "Broadcaster thread should be stopped.")

        # Check if server close was called
        mock_ws_server_instance.close.assert_called_once()
        mock_ws_server_instance.wait_closed.assert_called_once()


    async def test_register_and_unregister_client(self):
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)

        await self.interface._register_client(mock_websocket)
        self.assertIn(mock_websocket, self.interface.connected_clients)

        # Simulate subscription to unregister correctly
        instrument_id = "test_instr"
        async with self.interface.async_lock: # Lock for modifying subscriptions
            self.interface.subscriptions[instrument_id].add(mock_websocket)
            self.interface.client_subscriptions[mock_websocket].add(instrument_id)

        await self.interface._unregister_client(mock_websocket)
        self.assertNotIn(mock_websocket, self.interface.connected_clients)
        self.assertNotIn(mock_websocket, self.interface.client_subscriptions)
        # If it was the last client for 'test_instr', it should be removed from self.subscriptions
        # and an unsubscribe command sent to CTP.
        self.assertNotIn(instrument_id, self.interface.subscriptions)

        # Check if CTP command queue got an unsubscribe message
        try:
            cmd, data = self.ctp_command_queue.get_nowait()
            self.assertEqual(cmd, "unsubscribe")
            self.assertEqual(data, [instrument_id])
        except queue.Empty:
            self.fail("CTP command queue did not receive unsubscribe command.")


    async def test_handle_subscribe_action(self):
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.send = AsyncMock() # Mock the send method of the websocket

        instrument_id = "IF2302"
        await self.interface._handle_subscription(mock_websocket, instrument_id, subscribe=True)

        self.assertIn(mock_websocket, self.interface.subscriptions[instrument_id])
        self.assertIn(instrument_id, self.interface.client_subscriptions[mock_websocket])

        # Check that a subscribe command was sent to CTP
        cmd, data = self.ctp_command_queue.get_nowait()
        self.assertEqual(cmd, "subscribe")
        self.assertEqual(data, [instrument_id])

        # Check that a confirmation was sent to the client
        mock_websocket.send.assert_called_once_with(json.dumps({"status": "subscribed", "instrument": instrument_id}))


    async def test_handle_unsubscribe_action(self):
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.send = AsyncMock()

        instrument_id = "ag2302"
        # First, subscribe the client to the instrument
        async with self.interface.async_lock:
            self.interface.subscriptions[instrument_id].add(mock_websocket)
            self.interface.client_subscriptions[mock_websocket].add(instrument_id)

        # Now, handle unsubscription
        await self.interface._handle_subscription(mock_websocket, instrument_id, subscribe=False)

        self.assertNotIn(mock_websocket, self.interface.subscriptions.get(instrument_id, set()))
        self.assertNotIn(instrument_id, self.interface.client_subscriptions.get(mock_websocket, set()))
        if not self.interface.subscriptions.get(instrument_id): # If set is empty or key gone
            self.assertNotIn(instrument_id, self.interface.subscriptions)


        # Check that an unsubscribe command was sent to CTP (as it's the last client for this instrument)
        cmd, data = self.ctp_command_queue.get_nowait()
        self.assertEqual(cmd, "unsubscribe")
        self.assertEqual(data, [instrument_id])

        mock_websocket.send.assert_called_once_with(json.dumps({"status": "unsubscribed", "instrument": instrument_id}))

    async def test_message_handler_integration(self):
        # This is a more integrated test for the _message_handler itself
        mock_websocket = AsyncMock()
        mock_websocket.remote_address = ("127.0.0.1", 12345)
        mock_websocket.send = AsyncMock()

        # Simulate a stream of messages for the handler's loop
        # Correctly use a list of messages for the async iterator mock
        messages_to_receive = [
            json.dumps({"action": "subscribe", "instrument_id": "cu2303"}),
            json.dumps({"action": "unsubscribe", "instrument_id": "cu2303"}),
            json.dumps({"action": "invalid_action", "instrument_id": "xx2303"}),
            "this is not json", # Invalid JSON
            json.dumps({"instrument_id": "missing_action"}), # Missing action
        ]

        # Configure the mock websocket to behave like an async iterator
        mock_websocket.__aiter__.return_value = iter(messages_to_receive) # iter() for sync list
        # For async iterator behavior with proper async for loop, a more complex mock might be needed
        # or by using a helper like `async_iter`. For simplicity, this tests the message processing logic.
        # A better way to mock async iterator:
        async def async_message_generator():
            for msg in messages_to_receive:
                yield msg
            # Simulate connection close after messages
            raise websockets.exceptions.ConnectionClosedError(None, None)

        mock_websocket.__aiter__.return_value = async_message_generator()


        with patch.object(self.interface, '_register_client', AsyncMock()) as mock_reg, \
             patch.object(self.interface, '_unregister_client', AsyncMock()) as mock_unreg, \
             patch.object(self.interface, '_handle_subscription', AsyncMock()) as mock_handle_sub:

            await self.interface._message_handler(mock_websocket, "/somepath")

            mock_reg.assert_called_once_with(mock_websocket)

            # Check calls to _handle_subscription
            expected_handle_sub_calls = [
                call(mock_websocket, "cu2303", subscribe=True),
                call(mock_websocket, "cu2303", subscribe=False),
            ]
            mock_handle_sub.assert_has_calls(expected_handle_sub_calls)

            # Check calls to websocket.send for error messages
            expected_send_calls = [
                call(json.dumps({"status": "error", "message": "Unknown action: invalid_action"})),
                call(json.dumps({"status": "error", "message": "Invalid JSON format."})),
                call(json.dumps({"status": "error", "message": "Invalid message format. 'action' and 'instrument_id' required."})),
            ]
            # Allow any order for error messages as they might interleave with handler logic if not awaited properly
            # For precise order, ensure handler awaits send or use call_args_list inspection.
            mock_websocket.send.assert_has_calls(expected_send_calls, any_order=True)

            mock_unreg.assert_called_once_with(mock_websocket)


    def test_data_broadcaster_loop_single_client_single_instrument(self):
        # This test is for the synchronous part of the broadcaster loop logic
        # It needs a running event loop for run_coroutine_threadsafe

        # Setup a mock server_loop for the broadcaster
        mock_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(mock_loop) # Set as current loop for this thread for run_coroutine_threadsafe
        self.interface.server_loop = mock_loop

        mock_client = AsyncMock()
        mock_client.open = True
        mock_client.send = AsyncMock() # This will be called via run_coroutine_threadsafe

        instrument_id = "test_instr_broadcast"
        # Manually add subscription
        async def setup_subs(): # Needs to be async to use the async_lock
            async with self.interface.async_lock:
                self.interface.subscriptions[instrument_id].add(mock_client)
        mock_loop.run_until_complete(setup_subs())


        market_data = {"InstrumentID": instrument_id, "LastPrice": 123.45}
        self.data_input_queue.put(market_data)
        # self.data_input_queue.put(None) # Sentinel to allow loop to process and potentially exit if not running

        self.interface.running = True # Allow broadcaster to run one cycle

        # Run the broadcaster loop directly for one iteration or a short period
        # This is tricky because it's a thread. We'll check the effect.
        # Start it, let it process, then stop it.

        # Patch asyncio.run_coroutine_threadsafe before starting the thread
        with patch('asyncio.run_coroutine_threadsafe') as mock_run_coro:
            broadcaster_thread = threading.Thread(target=self.interface._data_broadcaster_loop, name="TestBroadcaster")
            broadcaster_thread.start()

            time.sleep(0.1) # Give broadcaster time to process the item

            self.interface.running = False # Signal it to stop
            broadcaster_thread.join(timeout=1.0)

            self.assertTrue(mock_run_coro.called)
            args, _ = mock_run_coro.call_args
            self.assertEqual(args[1], self.interface.server_loop)
            # Check that the coroutine passed was indeed client.send(json.dumps(market_data))
            # This involves inspecting the coroutine object, which can be complex.
            # For this test, we'll assume if it's called with the right loop and a coroutine, it's likely correct.
            # To be more precise, you could check the name of the coroutine if using Python 3.8+
            # self.assertIn("send", args[0].cr_code.co_name) # Example for Python 3.8+
            # Or ensure the mock_client.send was the one ultimately scheduled
            # This requires the run_coroutine_threadsafe to actually execute the coro in the mock_loop.
            # For that, the mock_loop would need to be running in the test thread, which it is not by default
            # when run_coroutine_threadsafe is used from another thread.

            # A practical way to check if send was attempted:
            # If run_coroutine_threadsafe was called, and its first argument (the coroutine)
            # is the `mock_client.send` method with the correct data, that's a good sign.
            # However, comparing the coroutine object itself is tricky.
            # We'll rely on the fact that it was called with *a* coroutine and the correct loop.
            # The actual send execution would be tested in an end-to-end test.

        mock_loop.close()


if __name__ == '__main__':
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)
    unittest.main()
