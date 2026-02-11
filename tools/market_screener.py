import os
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, List, Tuple

from dotenv import load_dotenv

from cloud_machine.kalshi_client import KalshiClient

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("cloud_machine")


@dataclass
class ScoredMarket:
    ticker: str
    close_ts: Optional[int]
    yes_bid: Optional[int]
    yes_ask: Optional[int]
    spread: Optional[int]
    top_depth: int
    score: float

def is_quicksettle(m: dict) -> bool:
    et = m.get("event_ticker") or ""
    return isinstance(et, str) and "QUICKSETTLE" in et

def parse_orderbook(ob_json: dict) -> Tuple[Optional[int], Optional[int], int]:
    """
    Returns (yes_bid, yes_ask, top_depth).
    YES ask is inferred from NO bids: yes_ask = 100 - best_no_bid. :contentReference[oaicite:7]{index=7}
    """
    book = (ob_json.get("orderbook") or {})
    yes = book.get("yes") or []
    no = book.get("no") or []

    yes_bid = max((px for px, _qty in yes), default=None)
    no_bid = max((px for px, _qty in no), default=None)
    yes_ask = None if no_bid is None else (100 - no_bid)

    # depth at top of book (qty at best levels)
    yes_top_qty = 0
    if yes_bid is not None:
        for px, qty in yes:
            if px == yes_bid:
                yes_top_qty = qty
                break

    no_top_qty = 0
    if no_bid is not None:
        for px, qty in no:
            if px == no_bid:
                no_top_qty = qty
                break

    top_depth = min(yes_top_qty, no_top_qty) if (yes_bid is not None and no_bid is not None) else 0
    return yes_bid, yes_ask, top_depth


def list_open_markets(client: KalshiClient, max_markets: int = 800) -> List[dict]:
    """
    Cursor pagination. :contentReference[oaicite:8]{index=8}
    """
    out: List[dict] = []
    cursor = None
    while len(out) < max_markets:
        path = "/trade-api/v2/markets?status=open&limit=200"
        if cursor:
            path += f"&cursor={cursor}"
        resp = client.get(path)
        batch = resp.get("markets") or []
        out.extend(batch)
        cursor = resp.get("cursor") or resp.get("next_cursor")
        if not cursor or not batch:
            break
        time.sleep(1)
    return out[:max_markets]


def iso_to_epoch(s: str) -> int | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        return int(dt.timestamp())
    except Exception:
        return None


def get_close_epoch(m: dict) -> int | None:
    close_s = m.get("close_time") or m.get("expiration_time") or m.get("latest_expiration_time")
    if isinstance(close_s, str):
        return iso_to_epoch(close_s)
    if isinstance(close_s, int):
        return close_s
    return None


def close_ts_ok(m: dict, min_days_out: int) -> bool:
    close_ts = get_close_epoch(m)
    if close_ts is None:
        return False
    now = int(datetime.now(timezone.utc).timestamp())
    return close_ts >= now + min_days_out * 86400


def score_market(spread: Optional[int], top_depth: int, volume: int = 0, open_interest: int = 0) -> float:
    if spread is None:
        return -1e9
    if spread <= 0:
        return -1e9
    # You can require spread >= 2 to focus on “okay spreads”
    return 50.0 * spread + 0.01 * top_depth + 0.001 * volume + 0.001 * open_interest


def fetch_score_one(client: KalshiClient, m: dict) -> ScoredMarket:
    ticker = m.get("ticker")
    close_ts = m.get("close_ts") or m.get("close_time") or m.get("close_time_ts") or m.get("close_timestamp")

    # if your market object exposes these, great; if not they stay 0
    volume = int(m.get("volume") or m.get("volume_24h") or 0)
    oi = int(m.get("open_interest") or 0)

    ob = client.get(f"/trade-api/v2/markets/{ticker}/orderbook")
    yes_bid, yes_ask, top_depth = parse_orderbook(ob)
    spread = None if (yes_bid is None or yes_ask is None) else (yes_ask - yes_bid)
    s = score_market(spread, top_depth, volume=volume, open_interest=oi)
    return ScoredMarket(
        ticker=ticker,
        close_ts=close_ts if isinstance(close_ts, int) else None,
        yes_bid=yes_bid,
        yes_ask=yes_ask,
        spread=spread,
        top_depth=top_depth,
        score=s,
    )


def main():
    load_dotenv()
    client = KalshiClient(
        api_key_id=os.environ["KALSHI_API_KEY_ID"],
        private_key_path=os.environ["KALSHI_PRIVATE_KEY_PATH"],
        env=os.environ.get("KALSHI_ENV", "prod"),  # read-only is fine; you can use demo too
    )

    MIN_DAYS_OUT = 14
    MAX_UNIVERSE = 5000
    SAMPLE_N = 50         # only fetch orderbooks for top N after filtering
    WORKERS = 8           # keep this modest for rate limits :contentReference[oaicite:9]{index=9}

    markets = list_open_markets(client, max_markets=MAX_UNIVERSE)
    markets = [m for m in markets if isinstance(m.get("ticker"), str)]
    markets = [m for m in markets if close_ts_ok(m, MIN_DAYS_OUT)]
    markets = [m for m in markets if not is_quicksettle(m)]

    # optional: pre-sort by volume/open_interest if present to choose which ones to sample
    def prekey(m: dict) -> int:
        return int(m.get("volume") or m.get("volume_24h") or m.get("open_interest") or 0)

    markets.sort(key=prekey, reverse=True)
    sample = markets[:SAMPLE_N]

    logger.info("universe=%d filtered=%d sample=%d (min_days_out=%d)", MAX_UNIVERSE, len(markets), len(sample), MIN_DAYS_OUT)

    scored: List[ScoredMarket] = []
    with ThreadPoolExecutor(max_workers=WORKERS) as ex:
        futs = [ex.submit(fetch_score_one, client, m) for m in sample]
        for f in as_completed(futs):
            try:
                scored.append(f.result())
            except Exception as e:
                logger.warning("fetch failed: %r", e)

    # keep “okay spreads”
    scored = [x for x in scored if x.spread is not None and x.spread >= 2]
    scored.sort(key=lambda x: x.score, reverse=True)

    logger.info("TOP 15:")
    for x in scored[:15]:
        close_str = "-"
        if x.close_ts:
            close_str = datetime.fromtimestamp(x.close_ts, tz=timezone.utc).strftime("%Y-%m-%d")
        logger.info(
            "ticker=%s close=%s yes=%s/%s spr=%s depth=%s score=%.2f",
            x.ticker, close_str, x.yes_bid, x.yes_ask, x.spread, x.top_depth, x.score
        )


if __name__ == "__main__":
    main()