import time

import config
import wifi
from display import Display
from stocks import fetch_quote, format_quote

display = Display()

UP_COLOR = (0, 200, 60)
DOWN_COLOR = (220, 30, 30)
NEUTRAL_COLOR = (200, 200, 200)
SCROLL_SPEED = getattr(config, "SCROLL_SPEED", 0.14)

quotes = {}


def refresh_quotes():
    wifi.ensure_connected()
    for symbol in config.TICKERS:
        quotes[symbol] = fetch_quote(symbol)


def run():
    display.scroll_text("PICOTICKER", NEUTRAL_COLOR, speed=SCROLL_SPEED)

    refresh_quotes()
    last_refresh = time.ticks_ms()

    while True:
        for symbol in config.TICKERS:
            if time.ticks_diff(time.ticks_ms(), last_refresh) >= config.QUOTE_REFRESH_INTERVAL * 1000:
                refresh_quotes()
                last_refresh = time.ticks_ms()

            quote = quotes.get(symbol)
            if quote is None:
                display.scroll_text("{} N/A".format(symbol), NEUTRAL_COLOR, speed=SCROLL_SPEED)
            else:
                price, change_percent = quote
                color = UP_COLOR if change_percent >= 0 else DOWN_COLOR
                display.scroll_text(format_quote(symbol, price, change_percent), color, speed=SCROLL_SPEED)


run()
