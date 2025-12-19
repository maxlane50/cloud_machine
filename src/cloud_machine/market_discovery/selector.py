# find which market to trade on today

import logging
import json
from datetime import datetime, date
from zoneinfo import ZoneInfo
from cloud_machine.kalshi_client import KalshiClient


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
logger = logging.getLogger("cloud_machine")

SERIES_TICKER = "KXHIGHCHI"

def get_today_chicago_high_temp_event(client: KalshiClient):
    # get all markets under Chicago high weather series with 'open' status
    resp = client.get(f"/trade-api/v2/events?series_ticker={SERIES_TICKER}&status=open")
    logger.info("raw response:\n%s", json.dumps(resp, indent=2))

    events_list = resp.get("events")

    CHICAGO_TZ = ZoneInfo("America/Chicago")
    today = datetime.now(CHICAGO_TZ).date()

    for event in events_list:
        dt = datetime.fromisoformat(event.get("strike_date").replace("Z", "+00:00"))
        if (dt.astimezone(CHICAGO_TZ).date() == today):
            return event.get("event_ticker")
        
    return "NO_TICKER"
