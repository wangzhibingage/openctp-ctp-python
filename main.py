import queue
import time
import signal
import os
import sys
import threading
import logging # Import logging module

# --- Logging Configuration ---
# Configure logging at the beginning of the script
logging.basicConfig(
    level=logging.INFO,  # Default logging level
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
# You can create specific loggers for each module if desired,
# but basicConfig will apply to all loggers unless they have specific handlers.
# For example, to make websockets library less verbose if it uses logging:
# logging.getLogger('websockets').setLevel(logging.WARNING)

logger = logging.getLogger(__name__) # Logger for the main application

# Attempt to import local modules
try:
    from ctp_connector import CTPConnector
    from data_processor import DataProcessor
    from client_interface import ClientInterface
except ImportError as e:
    logger.error(f"Error importing modules: {e}")
    logger.error("Ensure ctp_connector.py, data_processor.py, and client_interface.py are in the same directory or PYTHONPATH.")
    sys.exit(1)


# --- Configuration ---
MD_FRONT_ADDRESS = os.environ.get("MD_FRONT_ADDRESS", "tcp://180.168.146.187:10131")
CTP_BROKER_ID = os.environ.get("CTP_BROKER_ID", "9999")
CTP_USER_ID = os.environ.get("CTP_USER_ID", "")
CTP_PASSWORD = os.environ.get("CTP_PASSWORD", "")

GATEWAY_WEBSOCKET_HOST = os.environ.get("GATEWAY_WEBSOCKET_HOST", "0.0.0.0")
GATEWAY_WEBSOCKET_PORT = int(os.environ.get("GATEWAY_WEBSOCKET_PORT", 8765))

CTP_FLOW_PATH_ROOT = os.environ.get("CTP_FLOW_PATH_ROOT", ".")

# --- Global Variables ---
ctp_connector_instance = None
data_processor_instance = None
client_interface_instance = None
main_shutdown_event = threading.Event()


def shutdown_gateway(signum, frame):
    global ctp_connector_instance, data_processor_instance, client_interface_instance, main_shutdown_event
    logger.info(f"Shutdown signal {signum} received. Initiating gateway shutdown...")

    main_shutdown_event.set()

    if client_interface_instance:
        logger.info("Stopping Client Interface...")
        client_interface_instance.stop()
        # logger.info("Client Interface stopped.") # stop() methods should log

    if data_processor_instance:
        logger.info("Stopping Data Processor...")
        data_processor_instance.stop()
        # logger.info("Data Processor stopped.")

    if ctp_connector_instance:
        logger.info("Stopping CTP Connector...")
        ctp_connector_instance.stop()
        # logger.info("CTP Connector stopped.")

    logger.info("Gateway shutdown sequence complete. Exiting.")
    time.sleep(1) # Brief pause for logs to flush
    sys.exit(0)

def main():
    global ctp_connector_instance, data_processor_instance, client_interface_instance, main_shutdown_event

    signal.signal(signal.SIGINT, shutdown_gateway)
    signal.signal(signal.SIGTERM, shutdown_gateway)

    logger.info("Starting Futures Market Data Gateway...")
    logger.info(f"Configuration: MD_FRONT={MD_FRONT_ADDRESS}, BROKER_ID={CTP_BROKER_ID}, WS_HOST={GATEWAY_WEBSOCKET_HOST}, WS_PORT={GATEWAY_WEBSOCKET_PORT}, FLOW_ROOT={CTP_FLOW_PATH_ROOT}")

    market_data_to_processor_q = queue.Queue(maxsize=1000)
    processed_data_to_interface_q = queue.Queue(maxsize=1000)
    commands_to_ctp_q = queue.Queue(maxsize=100)

    logger.info(f"Initializing CTP Connector to {MD_FRONT_ADDRESS}...")
    try:
        ctp_connector_instance = CTPConnector(
            md_front=MD_FRONT_ADDRESS,
            broker_id=CTP_BROKER_ID,
            user_id=CTP_USER_ID,
            password=CTP_PASSWORD,
            data_queue=market_data_to_processor_q,
            command_queue=commands_to_ctp_q,
            flow_path_root=CTP_FLOW_PATH_ROOT
        )
    except Exception as e:
        logger.exception("CRITICAL: Failed to initialize CTPConnector.")
        sys.exit(1)

    logger.info("Initializing Data Processor...")
    try:
        data_processor_instance = DataProcessor(
            input_queue=market_data_to_processor_q,
            output_queue=processed_data_to_interface_q
        )
    except Exception as e:
        logger.exception("CRITICAL: Failed to initialize DataProcessor.")
        sys.exit(1)

    logger.info(f"Initializing Client Interface on {GATEWAY_WEBSOCKET_HOST}:{GATEWAY_WEBSOCKET_PORT}...")
    try:
        client_interface_instance = ClientInterface(
            host=GATEWAY_WEBSOCKET_HOST,
            port=GATEWAY_WEBSOCKET_PORT,
            data_input_queue=processed_data_to_interface_q,
            ctp_command_queue=commands_to_ctp_q
        )
    except Exception as e:
        logger.exception("CRITICAL: Failed to initialize ClientInterface.")
        sys.exit(1)

    logger.info("Starting CTP Connector...")
    ctp_connector_instance.connect()

    logger.info("Starting Data Processor...")
    data_processor_instance.start()

    logger.info("Starting Client Interface...")
    client_interface_instance.start()

    logger.info("Gateway is now running. Press Ctrl+C to stop.")

    try:
        while not main_shutdown_event.is_set():
            # Check component health (basic example)
            components_healthy = True
            if ctp_connector_instance and ctp_connector_instance.command_thread and not ctp_connector_instance.command_thread.is_alive() and ctp_connector_instance.running:
                logger.error("CRITICAL: CTPConnector command thread died unexpectedly!")
                components_healthy = False
            if data_processor_instance and data_processor_instance.thread and not data_processor_instance.thread.is_alive() and data_processor_instance.running:
                logger.error("CRITICAL: DataProcessor thread died unexpectedly!")
                components_healthy = False
            if client_interface_instance and client_interface_instance.server_thread and not client_interface_instance.server_thread.is_alive() and client_interface_instance.running:
                 logger.error("CRITICAL: ClientInterface server thread died unexpectedly!")
                 components_healthy = False

            if not components_healthy:
                logger.error("One or more critical components died. Initiating gateway shutdown.")
                main_shutdown_event.set() # Trigger shutdown

            main_shutdown_event.wait(timeout=5.0)

    except Exception as e:
        logger.exception("An unexpected error occurred in the main application loop.")
    finally:
        logger.info("Main loop exiting or shutdown initiated.")
        if not main_shutdown_event.is_set():
            logger.warning("Main loop finished unexpectedly, ensuring gateway shutdown...")
            shutdown_gateway(signal.SIGTERM, None)
        else:
            logger.info("Shutdown already in progress or completed via signal handler.")
        logger.info("Exiting main application.")


if __name__ == "__main__":
    if not os.path.exists(CTP_FLOW_PATH_ROOT):
        try:
            logger.info(f"Creating CTP flow path root directory: {CTP_FLOW_PATH_ROOT}")
            os.makedirs(CTP_FLOW_PATH_ROOT, exist_ok=True)
        except OSError as e:
            logger.warning(f"Error creating CTP flow path root directory {CTP_FLOW_PATH_ROOT}: {e}. This might cause issues for CTPConnector.")

    main()
