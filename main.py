import time

import config
import wifi
from display import Display
from stocks import fetch_market_open, fetch_quote, format_quote

display = Display()

UP_COLOR = (0, 200, 60)
DOWN_COLOR = (220, 30, 30)
NEUTRAL_COLOR = (200, 200, 200)
CLOSED_DIM_FACTOR = 0.35
SCROLL_SPEED = getattr(config, "SCROLL_SPEED", 0.14)
CLOSED_QUOTE_REFRESH_INTERVAL = getattr(config, "CLOSED_QUOTE_REFRESH_INTERVAL", 300)

quotes = {}
market_open = True  # assume open until the first market-status check


def dim(color):
    return tuple(int(c * CLOSED_DIM_FACTOR) for c in color)


def refresh_quotes():
    global market_open
    wifi.ensure_connected()

    status = fetch_market_open()
    if status is not None:
        market_open = status  # else keep the last known state

    for symbol in config.TICKERS:
        quotes[symbol] = fetch_quote(symbol)


def run():
    display.scroll_text("PICOTICKER", NEUTRAL_COLOR, speed=SCROLL_SPEED)

    refresh_quotes()
    last_refresh = time.ticks_ms()

    while True:
        for symbol in config.TICKERS:
            interval = config.QUOTE_REFRESH_INTERVAL if market_open else CLOSED_QUOTE_REFRESH_INTERVAL
            if time.ticks_diff(time.ticks_ms(), last_refresh) >= interval * 1000:
                refresh_quotes()
                last_refresh = time.ticks_ms()

            quote = quotes.get(symbol)
            if quote is None:
                display.scroll_text("{} N/A".format(symbol), NEUTRAL_COLOR, speed=SCROLL_SPEED)
            else:
                price, change_percent = quote
                color = UP_COLOR if change_percent >= 0 else DOWN_COLOR
                if not market_open:
                    color = dim(color)
                display.scroll_text(format_quote(symbol, price, change_percent), color, speed=SCROLL_SPEED)


run()
