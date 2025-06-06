import asyncio
import websockets
import json
import queue
import threading
import time
from collections import defaultdict
import logging # Import logging

logger = logging.getLogger(__name__) # Module-level logger

class ClientInterface:
    def __init__(self, host: str, port: int, data_input_queue: queue.Queue, ctp_command_queue: queue.Queue):
        self.host = host
        self.port = port
        self.data_input_queue = data_input_queue
        self.ctp_command_queue = ctp_command_queue

        self.connected_clients = set()
        self.subscriptions = defaultdict(set)
        self.client_subscriptions = defaultdict(set)

        # Use asyncio.Lock for async methods, and consider threading.Lock if shared with sync threads in complex ways.
        # For self.subscriptions and self.client_subscriptions, if _data_broadcaster_loop (sync thread)
        # needs to modify them, it would need a threading.Lock. Currently, it only reads.
        self.async_lock = asyncio.Lock()

        self.running = False
        self.data_broadcaster_thread = None
        self.server_thread = None
        self.server_loop = None
        self.websocket_server_instance = None # To keep track of the server instance for graceful shutdown

    async def _register_client(self, websocket):
        async with self.async_lock:
            self.connected_clients.add(websocket)
        logger.info(f"Client {websocket.remote_address} connected. Total clients: {len(self.connected_clients)}")

    async def _unregister_client(self, websocket):
        logger.info(f"Client {websocket.remote_address} disconnecting...")
        async with self.async_lock:
            if websocket in self.connected_clients:
                self.connected_clients.remove(websocket)

            instrument_ids_to_remove = list(self.client_subscriptions.get(websocket, set()))
            if websocket in self.client_subscriptions:
                del self.client_subscriptions[websocket]

            for instrument_id in instrument_ids_to_remove:
                if instrument_id in self.subscriptions:
                    if websocket in self.subscriptions[instrument_id]:
                        self.subscriptions[instrument_id].remove(websocket)
                    if not self.subscriptions[instrument_id]:
                        del self.subscriptions[instrument_id]
                        logger.info(f"Last client for {instrument_id} unsubscribed. Sending CTP unsubscribe command.")
                        try:
                            self.ctp_command_queue.put_nowait(("unsubscribe", [instrument_id]))
                        except queue.Full:
                            logger.warning(f"CTP command queue full. Failed to send unsubscribe for {instrument_id} upon last client leaving.")


        logger.info(f"Client {websocket.remote_address} disconnected. Total clients: {len(self.connected_clients)}")

    async def _handle_subscription(self, websocket, instrument_id: str, subscribe: bool = True):
        async with self.async_lock:
            if subscribe:
                self.subscriptions[instrument_id].add(websocket)
                self.client_subscriptions[websocket].add(instrument_id)
                try:
                    self.ctp_command_queue.put_nowait(("subscribe", [instrument_id]))
                    logger.info(f"Forwarded subscribe request for {instrument_id} from {websocket.remote_address} to CTP.")
                    await websocket.send(json.dumps({"status": "subscribed", "instrument": instrument_id}))
                except queue.Full:
                    logger.warning(f"CTP command queue full. Failed to send subscribe for {instrument_id}.")
                    # Rollback local subscription state
                    self.subscriptions[instrument_id].remove(websocket)
                    if not self.subscriptions[instrument_id]: del self.subscriptions[instrument_id]
                    self.client_subscriptions[websocket].remove(instrument_id)
                    if not self.client_subscriptions[websocket]: del self.client_subscriptions[websocket]
                    await websocket.send(json.dumps({"status": "error", "message": f"CTP command queue full, subscribe for {instrument_id} failed."}))
                    return # Important to return after rollback
                logger.debug(f"Client {websocket.remote_address} subscribed to {instrument_id}. Subscribers for {instrument_id}: {len(self.subscriptions[instrument_id])}")
            else: # Unsubscribe
                removed_from_instrument = False
                is_last_client_for_instrument = False
                if instrument_id in self.subscriptions and websocket in self.subscriptions[instrument_id]:
                    self.subscriptions[instrument_id].remove(websocket)
                    removed_from_instrument = True
                    if not self.subscriptions[instrument_id]:
                        del self.subscriptions[instrument_id]
                        is_last_client_for_instrument = True

                removed_from_client = False
                if websocket in self.client_subscriptions and instrument_id in self.client_subscriptions[websocket]:
                    self.client_subscriptions[websocket].remove(instrument_id)
                    removed_from_client = True
                    if not self.client_subscriptions[websocket]:
                         del self.client_subscriptions[websocket]

                if removed_from_instrument or removed_from_client:
                    logger.info(f"Client {websocket.remote_address} unsubscribed from {instrument_id}.")
                    await websocket.send(json.dumps({"status": "unsubscribed", "instrument": instrument_id}))
                    if is_last_client_for_instrument:
                        logger.info(f"Last client for {instrument_id} unsubscribed. Sending CTP unsubscribe command.")
                        try:
                            self.ctp_command_queue.put_nowait(("unsubscribe", [instrument_id]))
                        except queue.Full:
                            logger.warning(f"CTP command queue full. Failed to send unsubscribe for {instrument_id} upon last client unsubscription.")
                else:
                    logger.warning(f"Client {websocket.remote_address} tried to unsubscribe from {instrument_id} but was not subscribed or already unsubscribed.")
                    await websocket.send(json.dumps({"status": "error", "message": f"Not subscribed to {instrument_id} or already unsubscribed."}))

    async def _message_handler(self, websocket, path):
        await self._register_client(websocket)
        try:
            async for message in websocket:
                logger.debug(f"Received message from {websocket.remote_address}: {message}")
                try:
                    data = json.loads(message)
                    action = data.get("action")
                    instrument_id = data.get("instrument_id")

                    if not action or not instrument_id: # Basic validation
                        logger.warning(f"Invalid message from {websocket.remote_address}: {message}. 'action' and 'instrument_id' required.")
                        await websocket.send(json.dumps({"status": "error", "message": "Invalid message format. 'action' and 'instrument_id' required."}))
                        continue

                    if not isinstance(instrument_id, str) or not isinstance(action, str):
                        logger.warning(f"Invalid message type for action/instrument_id from {websocket.remote_address}: {message}.")
                        await websocket.send(json.dumps({"status": "error", "message": "Invalid type for 'action' or 'instrument_id'. Must be strings."}))
                        continue


                    if action == "subscribe":
                        await self._handle_subscription(websocket, instrument_id, subscribe=True)
                    elif action == "unsubscribe":
                        await self._handle_subscription(websocket, instrument_id, subscribe=False)
                    else:
                        logger.warning(f"Unknown action '{action}' from {websocket.remote_address}.")
                        await websocket.send(json.dumps({"status": "error", "message": f"Unknown action: {action}"}))

                except json.JSONDecodeError:
                    logger.warning(f"Invalid JSON from {websocket.remote_address}: {message}", exc_info=False)
                    await websocket.send(json.dumps({"status": "error", "message": "Invalid JSON format."}))
                except Exception as e:
                    logger.exception(f"Error handling message from {websocket.remote_address}.")
                    await websocket.send(json.dumps({"status": "error", "message": "Internal server error during message handling."}))

        except websockets.exceptions.ConnectionClosedError as e:
            logger.info(f"Connection closed by client {websocket.remote_address} (Code: {e.code}, Reason: '{e.reason}')")
        except Exception as e: # Catch other unexpected errors during the handler's lifecycle
            logger.exception(f"Unhandled error in client handler {websocket.remote_address}.")
        finally:
            await self._unregister_client(websocket)

    def _data_broadcaster_loop(self):
        logger.info("Data broadcaster thread started.")
        if not self.server_loop:
            logger.error("Server event loop not available for broadcaster. Exiting broadcaster.")
            return

        while self.running:
            try:
                market_data = self.data_input_queue.get(timeout=1)
                if market_data is None:
                    logger.debug("Broadcaster received None, continuing.")
                    continue

                instrument_id = market_data.get("InstrumentID")
                if not instrument_id:
                    logger.warning(f"Broadcaster received data without InstrumentID: {market_data}")
                    continue

                message_to_send = json.dumps(market_data)

                # Create a temporary list of subscribers to avoid issues if the set is modified during iteration by async code.
                # This read access to self.subscriptions is tricky because it's modified by async code with an asyncio.Lock.
                # A more robust way would be to use thread-safe mechanisms or pass copies.
                # For now, we assume this is mostly safe for read if modifications are quick.
                # A better approach: schedule the iteration and send part on the server_loop as well.
                subscribers_for_instrument = list(self.subscriptions.get(instrument_id, set()))
                logger.debug(f"Broadcasting {instrument_id} data to {len(subscribers_for_instrument)} clients.")


                if subscribers_for_instrument:
                    for client_ws in subscribers_for_instrument:
                        if client_ws.open:
                            # Schedule the send operation on the server's event loop
                            asyncio.run_coroutine_threadsafe(client_ws.send(message_to_send), self.server_loop)
                        else:
                            # Potentially handle dead client removal here if not caught by ping/pong or unregister
                            logger.debug(f"Client {client_ws.remote_address} for {instrument_id} is not open. Skipping send.")

            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("Error in data broadcaster.")

        logger.info("Data broadcaster thread stopped.")

    async def _start_server_async(self):
        # self.running should already be True
        self.server_loop = asyncio.get_running_loop()

        # Start the data broadcaster thread only after the server loop is captured
        self.data_broadcaster_thread = threading.Thread(target=self._data_broadcaster_loop, daemon=True, name="DataBroadcaster")
        self.data_broadcaster_thread.start()

        self.websocket_server_instance = await websockets.serve(self._message_handler, self.host, self.port)
        logger.info(f"WebSocket server started on ws://{self.host}:{self.port}")

        try:
            # Keep the server running as long as self.running is True
            while self.running:
                await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            logger.info("Server's main async task cancelled.")
        finally:
            logger.info("Stopping WebSocket server internals...")
            if self.websocket_server_instance:
                self.websocket_server_instance.close()
                await self.websocket_server_instance.wait_closed()
            logger.info("WebSocket server internals stopped.")


    def _run_async_server_wrapper(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        main_server_task = None
        try:
            main_server_task = loop.create_task(self._start_server_async())
            loop.run_until_complete(main_server_task)
        except KeyboardInterrupt:
            logger.info("Server loop interrupted by KeyboardInterrupt (from wrapper).")
        except Exception as e:
            logger.exception("Exception in _run_async_server_wrapper's event loop.")
        finally:
            self.running = False # Ensure this is set to stop other loops like broadcaster

            if main_server_task and not main_server_task.done():
                logger.info("Cancelling main server task...")
                main_server_task.cancel()
                # Wait for the task to actually cancel
                try:
                    loop.run_until_complete(main_server_task)
                except asyncio.CancelledError:
                    logger.info("Main server task successfully cancelled.")
                except Exception as e_cancel: #pylint: disable=broad-except
                    logger.error(f"Exception while waiting for main server task cancellation: {e_cancel}")


            if self.data_broadcaster_thread and self.data_broadcaster_thread.is_alive():
                 logger.debug("Joining data broadcaster thread in server wrapper...")
                 self.data_broadcaster_thread.join(timeout=2)

            logger.info("Shutting down async generators in server loop...")
            try:
                loop.run_until_complete(loop.shutdown_asyncgens())
            except Exception as e_gens: #pylint: disable=broad-except
                 logger.error(f"Exception during async generators shutdown: {e_gens}")

            logger.info("Closing server event loop...")
            loop.close()
            logger.info("Async server wrapper finished and event loop closed.")


    def start(self):
        if self.running:
            logger.info("ClientInterface already running.")
            return

        logger.info("Starting ClientInterface...")
        self.running = True # Set running before starting the thread
        self.server_thread = threading.Thread(target=self._run_async_server_wrapper, daemon=True, name="WebSocketServerThread")
        self.server_thread.start()
        logger.info("ClientInterface server thread started.")


    def stop(self):
        if not self.running and not (self.server_thread and self.server_thread.is_alive()):
            logger.info("ClientInterface already stopped or not started.")
            return

        logger.info("Stopping ClientInterface...")
        self.running = False # This will signal the async server and broadcaster to stop

        # Server thread manages its own loop and the broadcaster thread's lifecycle based on self.running
        if self.server_thread and self.server_thread.is_alive():
            logger.info("Joining server thread...")
            self.server_thread.join(timeout=5)
            if self.server_thread.is_alive():
                logger.warning("Server thread did not terminate in time.")

        # Ensure broadcaster is joined if server_thread didn't handle it fully (should not happen if logic is correct)
        if self.data_broadcaster_thread and self.data_broadcaster_thread.is_alive():
            logger.warning("Data broadcaster thread still alive after server thread join. Attempting to join again.")
            self.data_broadcaster_thread.join(timeout=2)

        logger.info("ClientInterface stopped.")


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, # DEBUG for verbose output in example
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    # Quieten down websockets library's own logging unless needed
    logging.getLogger('websockets').setLevel(logging.INFO)


    data_q = queue.Queue()
    ctp_cmd_q = queue.Queue()

    interface = ClientInterface(host="localhost", port=8765, data_input_queue=data_q, ctp_command_queue=ctp_cmd_q)

    main_stop_event = threading.Event()

    def data_producer():
        logger.info("DataProducer: Starting...")
        count = 0
        try:
            while not main_stop_event.is_set() and count < 100: # Increased count for longer test
                count += 1
                sample_instruments = ["instr_A", "instr_B", "instr_C"]
                instrument = sample_instruments[count % len(sample_instruments)]
                market_data = {
                    "InstrumentID": instrument,
                    "LastPrice": round(100.0 + count * 0.1, 2),
                    "Volume": 10 * count,
                    "UpdateTime": time.strftime("%H:%M:%S"),
                    "UpdateMillisec": int(time.time() * 1000) % 1000
                }
                data_q.put(market_data)
                logger.debug(f"DataProducer: Sent {instrument}")
                time.sleep(0.1) # Produce data faster
        except Exception as e:
            logger.exception("DataProducer: Error")
        finally:
            logger.info("DataProducer: Stopped.")

    def ctp_monitor():
        logger.info("CTPMonitor: Starting...")
        try:
            while not main_stop_event.is_set():
                try:
                    cmd = ctp_cmd_q.get(timeout=0.5)
                    logger.info(f"CTPMonitor: RX CTP CMD: {cmd}")
                except queue.Empty:
                    continue
        except Exception as e:
            logger.exception("CTPMonitor: Error")
        finally:
            logger.info("CTPMonitor: Stopped.")

    interface.start()

    producer_thread = threading.Thread(target=data_producer, daemon=True, name="TestProducer")
    producer_thread.start()

    ctp_monitor_thread = threading.Thread(target=ctp_monitor, daemon=True, name="TestCTPMonitor")
    ctp_monitor_thread.start()

    logger.info("ClientInterface Example: Server running. Connect via WebSocket e.g. ws://localhost:8765")
    logger.info("Send: {\"action\": \"subscribe\", \"instrument_id\": \"instr_A\"}")

    try:
        while True: # Keep main thread alive until Ctrl+C
            if not interface.server_thread or not interface.server_thread.is_alive():
                logger.error("ClientInterface server thread appears to have stopped unexpectedly. Exiting main loop.")
                break
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("ClientInterface Example: KeyboardInterrupt in main. Shutting down...")
    finally:
        main_stop_event.set()
        logger.info("Stopping ClientInterface...")
        interface.stop()

        logger.debug("Joining producer and monitor threads...")
        if producer_thread.is_alive(): producer_thread.join(timeout=2)
        if ctp_monitor_thread.is_alive(): ctp_monitor_thread.join(timeout=2)
        logger.info("ClientInterface Example: Main thread exited.")
