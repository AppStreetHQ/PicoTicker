import urequests

import config

QUOTE_URL = "https://finnhub.io/api/v1/quote"
MARKET_STATUS_URL = "https://finnhub.io/api/v1/stock/market-status"


def fetch_quote(symbol):
    """Return (price, change_percent) for a symbol, or None on failure."""
    url = "{}?symbol={}&token={}".format(QUOTE_URL, symbol, config.FINNHUB_API_KEY)
    response = None
    try:
        response = urequests.get(url)
        data = response.json()
        price = data.get("c")
        prev_close = data.get("pc")
        if not price or not prev_close:
            return None
        change_percent = (price - prev_close) / prev_close * 100
        return price, change_percent
    except Exception as exc:
        print("fetch_quote failed for", symbol, exc)
        return None
    finally:
        if response is not None:
            response.close()


def fetch_market_open():
    """Return True/False for whether the US market is open, or None on failure."""
    url = "{}?exchange=US&token={}".format(MARKET_STATUS_URL, config.FINNHUB_API_KEY)
    response = None
    try:
        response = urequests.get(url)
        data = response.json()
        return bool(data.get("isOpen"))
    except Exception as exc:
        print("fetch_market_open failed", exc)
        return None
    finally:
        if response is not None:
            response.close()


def format_quote(symbol, price, change_percent):
    arrow = "^" if change_percent >= 0 else "v"
    return "{} {:.2f} {}{:.2f}%".format(symbol, price, arrow, abs(change_percent))
