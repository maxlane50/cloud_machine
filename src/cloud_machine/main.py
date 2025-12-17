import time
import signal
import logging
import os
from datetime import datetime
from dotenv import load_dotenv
from cloud_machine.kalshi_client import KalshiClient
from cloud_machine.md_feed_poller import poll_kalshi

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)

running_ = True

def is_running() -> bool:
    return running_

def handle_sigterm(signum, frame) -> None:
    logging.info("received SIGTERM -- shutting down!")

    global running_
    running_ = False

signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

def main() -> int:
    logging.info("cloud_machine starting")

    global running_
    load_dotenv()

    client = KalshiClient(
        api_key_id=os.environ["KALSHI_API_KEY_ID"],
        private_key_path=os.environ["KALSHI_PRIVATE_KEY_PATH"],
        env=os.environ.get("KALSHI_ENV", "demo"),
    )

    ticker = "KXPRESPERSON-28" # president!
    # main polling loop
    poll_kalshi(client, is_running, ticker)

if __name__ == "__main__":
    main()
