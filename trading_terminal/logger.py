import logging
import time
import threading

# Configure logging to both console and a file
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("trading_terminal.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Heartbeat")

class Heartbeat:
    def __init__(self, interval=300): # 5 minutes default
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None

    def _run(self):
        while not self.stop_event.is_set():
            logger.info("Heartbeat: Trading Terminal is ALIVE and running.")
            # Wait for interval or until stop_event is set
            self.stop_event.wait(self.interval)

    def start(self):
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()
            logger.info("Heartbeat service started.")

    def stop(self):
        self.stop_event.set()
        logger.info("Heartbeat service stopping...")
