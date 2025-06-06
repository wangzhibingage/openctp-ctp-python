import queue
import threading
import time
import logging # Import logging

logger = logging.getLogger(__name__) # Module-level logger

class DataProcessor:
    def __init__(self, input_queue: queue.Queue, output_queue: queue.Queue):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.running = False
        self.thread = None

    def _process_data(self):
        logger.info("Processing thread started.")
        while self.running:
            try:
                raw_data = self.input_queue.get(timeout=1)

                if raw_data is None:
                    logger.debug("Received None (sentinel?), continuing.")
                    continue

                logger.debug(f"Received raw data: {raw_data.get('InstrumentID') if isinstance(raw_data, dict) else 'Unknown Instrument'}")

                # --- Data Transformation/Processing Logic ---
                # Example: Add a gateway timestamp
                # processed_data = raw_data.copy() if isinstance(raw_data, dict) else {} # Ensure it's a dict
                # processed_data['gateway_timestamp'] = time.time()

                processed_data = raw_data # Direct pass-through for now
                # --------------------------------------------

                if processed_data:
                    try:
                        self.output_queue.put(processed_data, timeout=1)
                        logger.debug(f"Put processed data to output queue: {processed_data.get('InstrumentID') if isinstance(processed_data, dict) else 'Unknown Instrument'}")
                    except queue.Full:
                        logger.warning("Output queue is full. Discarding data.")

            except queue.Empty:
                continue
            except Exception as e:
                logger.exception("Error processing data.") # Logs exception with traceback

        logger.info("Processing thread stopped.")

    def start(self):
        if self.running:
            logger.info("Already running.")
            return

        logger.info("Starting DataProcessor...")
        self.running = True
        self.thread = threading.Thread(target=self._process_data, daemon=True, name="DataProcessorThread")
        self.thread.start()
        logger.info("DataProcessor started.")

    def stop(self):
        if not self.running and not (self.thread and self.thread.is_alive()): # check thread as well
            logger.info("DataProcessor already stopped or not started.")
            return

        logger.info("Stopping DataProcessor...")
        self.running = False
        if self.thread and self.thread.is_alive():
            logger.debug("Joining DataProcessor thread...")
            self.thread.join(timeout=5)
            if self.thread.is_alive():
                logger.warning("Processing thread did not terminate in time.")
        logger.info("DataProcessor stopped.")

# Example Usage (for testing this module standalone)
if __name__ == '__main__':
    logging.basicConfig(
        level=logging.DEBUG, # Set to DEBUG for verbose output in example
        format='%(asctime)s - %(name)s - %(levelname)s - %(threadName)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    input_q = queue.Queue()
    output_q = queue.Queue()

    processor = DataProcessor(input_q, output_q)
    processor.start()

    logger.info("Main Example: Simulating data input...")
    for i in range(5):
        sample_data = {
            "InstrumentID": f"test_instr_{i}",
            "LastPrice": 100.0 + i,
            "Volume": 10 * i,
            "UpdateTime": time.strftime("%H:%M:%S"),
            "UpdateMillisec": int(time.time()*1000)%1000
        }
        input_q.put(sample_data)
        logger.debug(f"Main Example: Put sample data for {sample_data['InstrumentID']}")
        time.sleep(0.1) # Shorter sleep for faster test

    logger.info("Main Example: Checking output queue...")
    processed_count = 0
    for _ in range(5): # Try to get 5 items
        try:
            processed_data = output_q.get(timeout=1) # Shorter timeout
            logger.info(f"Main Example: Got processed data: {processed_data}")
            processed_count += 1
        except queue.Empty:
            logger.warning("Main Example: Output queue empty after timeout.")
            break # Exit loop if queue is empty

    if processed_count == 5:
        logger.info("Main Example: Successfully processed 5 data items.")
    else:
        logger.warning(f"Main Example: Processed only {processed_count} data items.")

    processor.stop()
    logger.info("Main Example: Exiting.")
