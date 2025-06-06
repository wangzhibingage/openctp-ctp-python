import thostmduserapi as mdapi
import queue
import time
import threading
import os
import logging # Import logging

# Each module can get its own logger
logger = logging.getLogger(__name__)

class CTPConnector(mdapi.CThostFtdcMdSpi):
    def __init__(self, md_front: str, broker_id: str, user_id: str, password: str, data_queue: queue.Queue, command_queue: queue.Queue, flow_path_root: str = "."):
        mdapi.CThostFtdcMdSpi.__init__(self)
        self.md_front = md_front
        self.broker_id = broker_id
        self.user_id = user_id
        self.password = password

        self.api = None
        self.req_id = 0
        self.is_connected = False
        self.is_logged_in = False
        self.running = False

        self.data_queue = data_queue
        self.command_queue = command_queue

        self.subscribed_instruments = set()
        self.subscription_lock = threading.Lock()

        self.flow_path = os.path.join(flow_path_root, "conn_flow", "md")
        if not os.path.exists(self.flow_path):
            try:
                os.makedirs(self.flow_path)
                logger.info(f"Created flow directory: {self.flow_path}")
            except OSError as e:
                logger.error(f"Error creating flow directory {self.flow_path}: {e}. Please ensure the path is writable.", exc_info=True)
                raise


    def connect(self):
        if self.api:
            logger.warning("API already created. Consider stopping and restarting for a fresh connection.")
            return

        logger.info(f"Using flow path: {self.flow_path}")
        self.api = mdapi.CThostFtdcMdApi.CreateFtdcMdApi(self.flow_path)
        if not self.api:
            logger.critical("Failed to create CThostFtdcMdApi instance. Check flow path and CTP library.")
            raise RuntimeError("Failed to create CThostFtdcMdApi instance.")

        self.api.RegisterFront(self.md_front)
        self.api.RegisterSpi(self)
        self.api.Init()
        self.running = True
        self.start_command_processor()
        logger.info("Init called and command processor started.")

    def login(self):
        if not self.is_connected:
            logger.warning("Not connected to front. Cannot login.")
            return

        if self.is_logged_in:
            logger.info("Already logged in.")
            return

        req = mdapi.CThostFtdcReqUserLoginField()
        req.BrokerID = self.broker_id
        req.UserID = self.user_id
        req.Password = self.password

        self.req_id += 1
        logger.info(f"Attempting login with ReqID: {self.req_id}, UserID: {self.user_id}, BrokerID: {self.broker_id}")
        ret = self.api.ReqUserLogin(req, self.req_id)
        if ret == 0:
            logger.info("Login request sent successfully.")
        else:
            logger.error(f"Login request failed. Error code: {ret}")

    def OnFrontConnected(self):
        logger.info("Front connected.")
        self.is_connected = True
        self.login()

    def OnFrontDisconnected(self, nReason: int):
        logger.warning(f"Front disconnected. Reason: {hex(nReason)}")
        self.is_connected = False
        self.is_logged_in = False

    def _decode_gbk_string(self, byte_string, default_if_error="<decode_error>"):
        if byte_string is None:
            return ""
        try:
            return byte_string.decode('gbk').strip()
        except AttributeError:
            return str(byte_string).strip()
        except UnicodeDecodeError:
            try:
                return byte_string.decode('utf-8').strip() # Try UTF-8 as a fallback
            except UnicodeDecodeError:
                logger.warning(f"Could not decode byte string with GBK or UTF-8: {byte_string!r}", exc_info=False) # Log only the message
                return default_if_error


    def OnRspUserLogin(self, pRspUserLogin: mdapi.CThostFtdcRspUserLoginField, pRspInfo: mdapi.CThostFtdcRspInfoField, nRequestID: int, bIsLast: bool):
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            error_msg = self._decode_gbk_string(pRspInfo.ErrorMsg)
            logger.error(f"Login failed. ReqID: {nRequestID}, ErrorID: {pRspInfo.ErrorID}, ErrorMsg: {error_msg}")
            self.is_logged_in = False
        else:
            user_id_str = self._decode_gbk_string(pRspUserLogin.UserID)
            trading_day_str = self._decode_gbk_string(pRspUserLogin.TradingDay)
            logger.info(f"Login successful. ReqID: {nRequestID}, TradingDay: {trading_day_str}, UserID: {user_id_str}")
            self.is_logged_in = True
            self._resubscribe_instruments()

    def _resubscribe_instruments(self):
        with self.subscription_lock:
            if self.subscribed_instruments:
                instruments_to_resubscribe = list(self.subscribed_instruments)
                if instruments_to_resubscribe:
                    logger.info(f"Resubscribing to {len(instruments_to_resubscribe)} instruments: {instruments_to_resubscribe}")
                    self._internal_subscribe(instruments_to_resubscribe, is_resubscribe=True)

    def _internal_subscribe(self, instrument_ids: list, is_resubscribe: bool = False):
        if not self.is_logged_in:
            if is_resubscribe:
                logger.warning("(Resubscribe) Not logged in. Will attempt later if login succeeds.")
            else:
                logger.warning("Not logged in. Cannot subscribe to market data.")
            return

        actual_instruments_to_subscribe = []
        if is_resubscribe:
            actual_instruments_to_subscribe = instrument_ids
        else:
            with self.subscription_lock:
                for inst_id in instrument_ids:
                    if inst_id not in self.subscribed_instruments:
                        actual_instruments_to_subscribe.append(inst_id)

        if not actual_instruments_to_subscribe:
            if not is_resubscribe:
                logger.info(f"Instruments {instrument_ids} already subscribed or empty list provided.")
            return

        encoded_instrument_ids = [inst_id.encode('utf-8') for inst_id in actual_instruments_to_subscribe]
        self.req_id += 1
        logger.info(f"Sending SubscribeMarketData request (ReqID: {self.req_id}) for: {actual_instruments_to_subscribe}")
        ret = self.api.SubscribeMarketData(encoded_instrument_ids, len(encoded_instrument_ids))

        if ret == 0:
            logger.info(f"SubscribeMarketData request sent successfully for {actual_instruments_to_subscribe}.")
        else:
            logger.error(f"SubscribeMarketData request failed for {actual_instruments_to_subscribe}. Error code: {ret}")


    def subscribe_market_data(self, instrument_ids: list):
        self._internal_subscribe(instrument_ids)

    def unsubscribe_market_data(self, instrument_ids: list):
        if not self.is_logged_in:
            logger.warning("Not logged in. Cannot unsubscribe market data.")
            return

        with self.subscription_lock:
            instruments_to_unsubscribe = [inst_id for inst_id in instrument_ids if inst_id in self.subscribed_instruments]
            if not instruments_to_unsubscribe:
                logger.info(f"Instruments {instrument_ids} not currently subscribed or empty list.")
                return

            encoded_instrument_ids = [inst_id.encode('utf-8') for inst_id in instruments_to_unsubscribe]
            self.req_id += 1
            logger.info(f"Sending UnSubscribeMarketData request (ReqID: {self.req_id}) for: {instruments_to_unsubscribe}")
            ret = self.api.UnSubscribeMarketData(encoded_instrument_ids, len(encoded_instrument_ids))

            if ret == 0:
                logger.info(f"UnSubscribeMarketData request sent successfully for {instruments_to_unsubscribe}.")
            else:
                logger.error(f"UnSubscribeMarketData request failed for {instruments_to_unsubscribe}. Error code: {ret}")


    def OnRspSubMarketData(self, pSpecificInstrument: mdapi.CThostFtdcSpecificInstrumentField, pRspInfo: mdapi.CThostFtdcRspInfoField, nRequestID: int, bIsLast: bool):
        instrument_id = self._decode_gbk_string(pSpecificInstrument.InstrumentID)
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            error_msg = self._decode_gbk_string(pRspInfo.ErrorMsg)
            logger.error(f"Subscribe failed for {instrument_id} (ReqID: {nRequestID}). ErrorID: {pRspInfo.ErrorID}, ErrorMsg: {error_msg}")
        else:
            logger.info(f"Subscribe successful for {instrument_id} (ReqID: {nRequestID}).")
            with self.subscription_lock:
                self.subscribed_instruments.add(instrument_id)
                logger.debug(f"Added {instrument_id} to subscribed list. Current: {list(self.subscribed_instruments)}")


    def OnRspUnSubMarketData(self, pSpecificInstrument: mdapi.CThostFtdcSpecificInstrumentField, pRspInfo: mdapi.CThostFtdcRspInfoField, nRequestID: int, bIsLast: bool):
        instrument_id = self._decode_gbk_string(pSpecificInstrument.InstrumentID)
        if pRspInfo is not None and pRspInfo.ErrorID != 0:
            error_msg = self._decode_gbk_string(pRspInfo.ErrorMsg)
            logger.error(f"Unsubscribe failed for {instrument_id} (ReqID: {nRequestID}). ErrorID: {pRspInfo.ErrorID}, ErrorMsg: {error_msg}")
        else:
            logger.info(f"Unsubscribe successful for {instrument_id} (ReqID: {nRequestID}).")
            with self.subscription_lock:
                if instrument_id in self.subscribed_instruments:
                    self.subscribed_instruments.remove(instrument_id)
                    logger.debug(f"Removed {instrument_id} from subscribed list. Current: {list(self.subscribed_instruments)}")
                else:
                    logger.warning(f"{instrument_id} was not in subscribed list for removal (unsub confirmation).")

    def _safe_float(self, value, default=0.0):
        return value if value is not None and value < float('inf') and value > float('-inf') else default

    def OnRtnDepthMarketData(self, pDepthMarketData: mdapi.CThostFtdcDepthMarketDataField):
        instrument_id_str = self._decode_gbk_string(pDepthMarketData.InstrumentID, "UnknownInstrument")
        try:
            # More verbose logging for received data can be set to DEBUG level
            logger.debug(f"Received DepthMarketData for {instrument_id_str} - LastPrice: {pDepthMarketData.LastPrice}, Volume: {pDepthMarketData.Volume}")

            data_copy = {
                "InstrumentID": instrument_id_str,
                "LastPrice": self._safe_float(pDepthMarketData.LastPrice),
                "Volume": pDepthMarketData.Volume,
                "UpdateTime": self._decode_gbk_string(pDepthMarketData.UpdateTime),
                "UpdateMillisec": pDepthMarketData.UpdateMillisec,
                "BidPrice1": self._safe_float(pDepthMarketData.BidPrice1),
                "BidVolume1": pDepthMarketData.BidVolume1,
                "AskPrice1": self._safe_float(pDepthMarketData.AskPrice1),
                "AskVolume1": pDepthMarketData.AskVolume1,
                "OpenInterest": self._safe_float(pDepthMarketData.OpenInterest),
                "TradingDay": self._decode_gbk_string(pDepthMarketData.TradingDay),
                "ExchangeID": self._decode_gbk_string(pDepthMarketData.ExchangeID),
                "OpenPrice": self._safe_float(pDepthMarketData.OpenPrice),
                "HighestPrice": self._safe_float(pDepthMarketData.HighestPrice),
                "LowestPrice": self._safe_float(pDepthMarketData.LowestPrice),
                "ClosePrice": self._safe_float(pDepthMarketData.ClosePrice),
                "SettlementPrice": self._safe_float(pDepthMarketData.SettlementPrice),
                "PreClosePrice": self._safe_float(pDepthMarketData.PreClosePrice),
                "PreSettlementPrice": self._safe_float(pDepthMarketData.PreSettlementPrice),
                "PreOpenInterest": self._safe_float(pDepthMarketData.PreOpenInterest),
                "UpperLimitPrice": self._safe_float(pDepthMarketData.UpperLimitPrice),
                "LowerLimitPrice": self._safe_float(pDepthMarketData.LowerLimitPrice),
                "AveragePrice": self._safe_float(pDepthMarketData.AveragePrice), # Often not populated for futures
                "ActionDay": self._decode_gbk_string(pDepthMarketData.ActionDay),
            }
            self.data_queue.put(data_copy)
        except Exception as e:
            logger.exception(f"Error processing/decoding market data for {instrument_id_str}.")


    def _process_commands(self):
        logger.info("Command processing thread started.")
        while self.running:
            try:
                command, data = self.command_queue.get(timeout=1)
                logger.debug(f"Received command: {command} with data: {data}")
                if command == "subscribe":
                    self.subscribe_market_data(data)
                elif command == "unsubscribe":
                    self.unsubscribe_market_data(data)
                elif command == "shutdown":
                    logger.info("Shutdown command received by command processor.")
                    break
            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("Error in command processing loop.")
        logger.info("Command processing thread stopped.")

    def start_command_processor(self):
        self.command_thread = threading.Thread(target=self._process_commands, daemon=True, name="CTPCommandProcessor")
        self.command_thread.start()

    def stop(self):
        logger.info("Stopping CTPConnector...")
        self.running = False

        if hasattr(self, 'command_queue') and self.command_queue is not None:
            try:
                self.command_queue.put(("shutdown", None), timeout=1.0)
            except queue.Full:
                logger.warning("Command queue full, unable to send shutdown signal directly to command processor.")


        if hasattr(self, 'command_thread') and self.command_thread.is_alive():
            logger.info("Joining command thread...")
            self.command_thread.join(timeout=5)
            if self.command_thread.is_alive():
                logger.warning("Command thread did not terminate in time.")

        if self.api:
            logger.info("Releasing CTP API resources (simulated - actual Release() call omitted for subtask stability).")
            # In a real app:
            # self.api.RegisterSpi(None)
            # self.api.Release()
            self.api = None

        self.is_connected = False
        self.is_logged_in = False
        logger.info("CTPConnector stopped.")

# Example Usage (for testing this module standalone)
if __name__ == '__main__':
    # Setup basic logging for the example
    logging.basicConfig(
        level=logging.DEBUG, # Use DEBUG for more verbose output from CTPConnector
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    MD_FRONT = "tcp://180.168.146.187:10131"
    BROKER_ID = "9999"
    USER_ID = ""
    PASSWORD = ""

    data_q = queue.Queue()
    cmd_q = queue.Queue()

    logger.info(f"Main Example: Attempting to connect to MD Front: {MD_FRONT}")
    connector = CTPConnector(MD_FRONT, BROKER_ID, USER_ID, PASSWORD, data_q, cmd_q, flow_path_root=".")

    main_stop_event = threading.Event()

    def shutdown_handler(signum, frame):
        logger.info("Main Example: Shutdown signal received.")
        main_stop_event.set()

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    try:
        connector.connect()

        login_timeout_seconds = 10
        start_time = time.time()
        while not connector.is_logged_in and (time.time() - start_time) < login_timeout_seconds and not main_stop_event.is_set():
            logger.debug(f"Main Example: Waiting for login... Connected: {connector.is_connected}, LoggedIn: {connector.is_logged_in}")
            time.sleep(1)

        if connector.is_logged_in:
            logger.info("Main Example: Successfully logged in.")
            cmd_q.put(("subscribe", ["au2406", "ag2406", "IF2406"]))

            listen_duration = 20
            end_listen_time = time.time() + listen_duration

            while time.time() < end_listen_time and not main_stop_event.is_set():
                if not connector.is_logged_in and not connector.is_connected:
                    logger.warning("Main Example: Disconnected during listening.")
                    break
                try:
                    market_data = data_q.get(timeout=1)
                    logger.info(f"Main Example: RX DepthMarketData: Inst:{market_data.get('InstrumentID')}, LP:{market_data.get('LastPrice')}, Vol:{market_data.get('Volume')}, AskP1:{market_data.get('AskPrice1')}, BidP1:{market_data.get('BidPrice1')}")
                except queue.Empty:
                    pass
                except Exception as e:
                    logger.exception("Main Example: Error getting data from queue.")

            if not main_stop_event.is_set(): # Only if not already shutting down
                if not connector.is_connected and not connector.is_logged_in:
                     logger.warning("Main Example: Lost connection before unsubscribe/subscribe.")
                else:
                    logger.info("Main Example: Attempting to unsubscribe from 'au2406'...")
                    cmd_q.put(("unsubscribe", ["au2406"]))
                    time.sleep(2)

                    logger.info("Main Example: Attempting to subscribe to 'cu2406'...")
                    cmd_q.put(("subscribe", ["cu2406"]))
                    time.sleep(5) # Listen for a bit more if not shutting down
        else:
            logger.error(f"Main Example: Could not login to CTP MD server at {MD_FRONT} within {login_timeout_seconds}s.")
            if not connector.is_connected:
                logger.error("Main Example: Failed to connect to the front server.")

    except RuntimeError as e:
        logger.exception("Main Example: Runtime error during CTP connection.")
    except Exception as e: # Catch any other unexpected errors
        logger.exception("Main Example: An unexpected error occurred.")
    finally:
        logger.info("Main Example: Shutting down CTPConnector...")
        if not main_stop_event.is_set(): # If loop exited for other reason than signal
             main_stop_event.set() # Ensure other parts know we're stopping
        connector.stop()
        logger.info("Main Example: Exiting.")
