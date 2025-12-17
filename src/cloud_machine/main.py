import time
import signal
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)

_running = True

def handle_sigterm(signum, frame):
    global _running
    logging.info("received SIGTERM, shutting down cleanly")
    _running = False

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def main():
    logging.info("cloud_machine starting")

    while _running:
        logging.info("heartbeat %s", datetime.utcnow().isoformat())
        time.sleep(5)

    logging.info("cloud_machine exited cleanly")

if __name__ == "__main__":
    main()
