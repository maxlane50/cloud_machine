import os
import time
import logging
import json
import requests
from cloud_machine.kalshi_client import KalshiClient
from cloud_machine.market_discovery.selector import get_today_chicago_high_temp_event
#from cloud_machine.market_discovery.selector import get_market_tickers_from_event


TICKER = "KXPRESPERSON-28-JVAN"
POLL_INTERVAL_SECONDS = 5
logger = logging.getLogger("cloud_machine")

def parse_bbos(ob_json: dict):
    book = ob_json.get("orderbook", {}) or {}
    yes = book.get("yes", []) or []
    no = book.get("no", []) or []

    best_yes_bid = max((px for px, _qty in yes), default=None)
    best_no_bid = max((px for px, _qty in no), default=None)

    best_yes_ask = None if best_no_bid is None else (100 - best_no_bid)

    return best_yes_bid, best_yes_ask

def poll_kalshi(client: KalshiClient, is_running_cb) -> None:

    # find the ticker for current high temp event
    chi_temp_event = get_today_chicago_high_temp_event(client)

    # within that event, fetch the tickers for the different temps
    market_tickers = get_market_tickers_from_event(event)

    # for now, just pick the first
    # TODO: select by highest volume
    ticker = market_tickers[0]

    logger.info("today event_ticker=%s", event.get("event_ticker"))
    logger.info("found %d market tickers", len(market_tickers))
    logger.info("market tickers=%s", market_tickers)

    

    while is_running_cb():
        try:
            book = client.get(f"/trade-api/v2/markets/{TICKER}/orderbook")
            bid, ask = parse_bbos(book)
            midpoint = (None if (bid is None or ask is None) else (bid + ask) / 2.0)
            logger.info("ticker=%s, bid=%s, ask=%s, mid=%s", TICKER, bid, ask, midpoint)
        except Exception as e:
            logger.warning("polling error: %r", e)

        for _ in range(POLL_INTERVAL_SECONDS):
            if not is_running_cb():
                break
            time.sleep(1)

    logger.info("poller exited cleanly")
