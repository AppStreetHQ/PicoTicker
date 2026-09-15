import urequests

import config

QUOTE_URL = "https://finnhub.io/api/v1/quote"
MARKET_STATUS_URL = "https://finnhub.io/api/v1/stock/market-status"
SEARCH_URL = "https://finnhub.io/api/v1/search"

# Confirmed against the real device: urequests.get()'s timeout kwarg is
# genuinely enforced at the socket level here (a request to a
# deliberately black-holed address failed at exactly the requested
# timeout, not indefinitely). Without it, a TCP connection that stalls
# mid-request rather than erroring — the same silent-failure class as
# finnhub_ws.py's stale-websocket problem, just on the REST side —
# blocks forever with nothing to raise for the try/except below to
# catch, wedging fetch_loop() with no diagnostic. Finnhub's own
# latency is normally well under a second, so this is generous.
REQUEST_TIMEOUT_SECONDS = 5


def _fetch_quote_json(symbol):
    url = "{}?symbol={}&token={}".format(QUOTE_URL, symbol, config.FINNHUB_API_KEY)
    response = None
    try:
        response = urequests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        return response.json()
    finally:
        if response is not None:
            response.close()


def fetch_quote(symbol):
    """Return (price, change_percent) for a symbol, or None on failure."""
    try:
        data = _fetch_quote_json(symbol)
        price = data.get("c")
        prev_close = data.get("pc")
        if not price or not prev_close:
            return None
        change_percent = (price - prev_close) / prev_close * 100
        return price, change_percent
    except Exception as exc:
        print("fetch_quote failed for", symbol, exc)
        return None


def fetch_prev_close(symbol):
    """Return just the previous close for a symbol, or None on failure.
    Used to seed live_quotes' % change baseline — the trades websocket
    only ever streams a raw price, never a prev-close to compare it
    against."""
    try:
        data = _fetch_quote_json(symbol)
        prev_close = data.get("pc")
        return prev_close if prev_close else None
    except Exception as exc:
        print("fetch_prev_close failed for", symbol, exc)
        return None


def fetch_market_open():
    """Return True/False for whether the US market is open, or None on
    failure — including a response that came back with no "isOpen"
    field at all (a malformed/truncated/unexpected body, e.g. from a
    network hiccup — Finnhub sits behind Cloudflare). That's genuinely
    ambiguous, not "definitely closed": bool(data.get("isOpen")) would
    silently treat a missing field the same as an explicit False,
    which could dim the display while the market's actually open with
    nothing in the logs to explain why. A real "closed" answer from
    Finnhub is always an explicit boolean, never a missing key."""
    url = "{}?exchange=US&token={}".format(MARKET_STATUS_URL, config.FINNHUB_API_KEY)
    response = None
    try:
        response = urequests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        data = response.json()
        is_open = data.get("isOpen")
        if is_open is None:
            print("fetch_market_open: no isOpen field in response:", data)
            return None
        return bool(is_open)
    except Exception as exc:
        print("fetch_market_open failed", exc)
        return None
    finally:
        if response is not None:
            response.close()


def symbol_exists(symbol):
    """Check Finnhub's symbol lookup for a real, exact-match ticker.
    True/False when Finnhub actually answered; None if the check itself
    failed (API/network issue) — that's "unknown", not "invalid", so
    callers shouldn't reject a symbol just because this came back None."""
    url = "{}?q={}&token={}".format(SEARCH_URL, symbol, config.FINNHUB_API_KEY)
    response = None
    try:
        response = urequests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        data = response.json()
        for result in data.get("result", []):
            if result.get("symbol") == symbol:
                return True
        return False
    except Exception as exc:
        print("symbol_exists failed for", symbol, exc)
        return None
    finally:
        if response is not None:
            response.close()


def format_quote(symbol, price, change_percent):
    arrow = "^" if change_percent >= 0 else "v"
    return "{} {:.2f} {}{:.2f}%".format(symbol, price, arrow, abs(change_percent))
