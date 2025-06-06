import unittest
from unittest.mock import MagicMock, patch
import queue
import time
import logging

# Ensure client_interface can be imported
import sys
import os
# Add the directory containing the modules to sys.path
# Assuming the test file is in the same directory as the modules or a subdirectory
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    from data_processor import DataProcessor
except ImportError:
    # Fallback if the above path adjustment doesn't work in the execution environment
    # This might happen if the script is run from a different working directory
    # For the purpose of this subtask, we assume data_processor is findable.
    # If not, the subtask environment needs to ensure module visibility.
    logging.error("Failed to import DataProcessor. Ensure it's in PYTHONPATH or accessible.")
    # Create a dummy class if import fails, so the rest of the test file is valid syntax
    class DataProcessor:
        def __init__(self, iq, oq): pass
        def start(self): pass
        def stop(self): pass


# Disable logging for cleaner test output, can be enabled for debugging
# logging.disable(logging.CRITICAL)

class TestDataProcessor(unittest.TestCase):

    def setUp(self):
        self.input_queue = queue.Queue()
        self.output_queue = queue.Queue()
        self.processor = DataProcessor(self.input_queue, self.output_queue)
        # Suppress logging output during tests unless specifically testing logging
        # logging.getLogger('data_processor').setLevel(logging.CRITICAL + 1)


    def tearDown(self):
        if self.processor and self.processor.running:
            self.processor.stop()
        # Clear queues
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except queue.Empty:
                break
        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except queue.Empty:
                break

    def test_initialization(self):
        self.assertIsNotNone(self.processor)
        self.assertFalse(self.processor.running)
        self.assertIsNone(self.processor.thread)

    def test_start_and_stop(self):
        self.processor.start()
        self.assertTrue(self.processor.running)
        self.assertIsNotNone(self.processor.thread)
        self.assertTrue(self.processor.thread.is_alive())

        # Give a moment for the thread to actually start its loop
        time.sleep(0.01)

        self.processor.stop()
        # The stop method should join the thread, so it might take a moment
        # The timeout in stop() is 5 seconds. We expect it to be much faster.
        time.sleep(0.1) # Allow time for thread to join
        self.assertFalse(self.processor.running)
        # Thread should be joined by stop()
        self.assertFalse(self.processor.thread.is_alive())

    def test_start_already_running(self):
        self.processor.start()
        initial_thread = self.processor.thread
        # Mock logger to check if "Already running" is logged (optional)
        with patch.object(logging.getLogger('data_processor'), 'info') as mock_log_info:
            self.processor.start() # Try starting again
            mock_log_info.assert_any_call("Already running.")
        self.assertIs(self.processor.thread, initial_thread) # Thread should be the same
        self.processor.stop()

    def test_stop_not_running(self):
        # Mock logger to check if "Not running" is logged
        with patch.object(logging.getLogger('data_processor'), 'info') as mock_log_info:
            self.processor.stop()
            # It might log "already stopped or not started"
            # Check if any call contains "stopped" or "not running"
            called_with_expected_message = False
            for call_args in mock_log_info.call_args_list:
                if "already stopped" in call_args[0][0] or "not running" in call_args[0][0]:
                    called_with_expected_message = True
                    break
            self.assertTrue(called_with_expected_message, "Expected log message for stopping when not running not found.")
        self.assertFalse(self.processor.running)


    def test_data_pass_through(self):
        self.processor.start()

        sample_data_1 = {"id": 1, "value": "test1"}
        sample_data_2 = {"id": 2, "value": "test2"}

        self.input_queue.put(sample_data_1)
        self.input_queue.put(sample_data_2)

        try:
            processed_1 = self.output_queue.get(timeout=1)
            processed_2 = self.output_queue.get(timeout=1)
        except queue.Empty:
            self.fail("Output queue was empty, expected data.")

        self.assertEqual(processed_1, sample_data_1)
        self.assertEqual(processed_2, sample_data_2)

        self.processor.stop()

    def test_empty_input_queue_stays_running(self):
        self.processor.start()
        time.sleep(0.1) # Let it run for a bit with an empty queue
        self.assertTrue(self.processor.running)
        self.assertTrue(self.processor.thread.is_alive())
        self.processor.stop()

    def test_processing_none_value(self):
        self.processor.start()
        self.input_queue.put(None) # Sentinel value or erroneous None
        # The processor should not crash and should continue running.
        # It should not put None into the output queue if it's a sentinel.
        time.sleep(0.1)
        self.assertTrue(self.output_queue.empty())
        self.processor.stop()

    def test_output_queue_full(self):
        # Make output queue small
        self.output_queue = queue.Queue(maxsize=1)
        self.processor.output_queue = self.output_queue # Re-assign

        self.processor.start()

        self.input_queue.put({"id": 1, "data": "first"})
        try:
            item1 = self.output_queue.get(timeout=0.5)
            self.assertIsNotNone(item1)
        except queue.Empty:
            self.fail("Failed to get the first item from output queue.")

        # Output queue is now full. Put another item.
        self.input_queue.put({"id": 2, "data": "second"})
        # The processor should log a warning and discard.
        # Give it time to process and try to put.

        with patch.object(logging.getLogger('data_processor'), 'warning') as mock_log_warning:
            time.sleep(0.2) # Time for the processor to try putting to full queue
            # The second item should be discarded or handled. The current implementation discards.
            # Check if the warning was logged
            mock_log_warning.assert_any_call("Output queue is full. Discarding data.")

        # Ensure no new item was added to output queue
        with self.assertRaises(queue.Empty):
            self.output_queue.get_nowait()

        self.processor.stop()

if __name__ == '__main__':
    # Setup logging for the test run itself if needed, especially for debugging tests
    logging.basicConfig(stream=sys.stderr, level=logging.DEBUG,
                        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    unittest.main()
