import time

import config
from display import Display
from stocks import fetch_quote, format_quote

display = Display()

UP_COLOR = (0, 200, 60)
DOWN_COLOR = (220, 30, 30)
NEUTRAL_COLOR = (200, 200, 200)


def run():
    display.scroll_text("PICOTICKER", NEUTRAL_COLOR)

    while True:
        for symbol in config.TICKERS:
            quote = fetch_quote(symbol)
            if quote is None:
                display.scroll_text("{} N/A".format(symbol), NEUTRAL_COLOR)
            else:
                price, change_percent = quote
                color = UP_COLOR if change_percent >= 0 else DOWN_COLOR
                display.scroll_text(format_quote(symbol, price, change_percent), color)
            time.sleep(config.POLL_INTERVAL)


run()
