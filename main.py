import time

import _thread

import clock
import config
import market
import web
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
FETCH_THROTTLE_SECONDS = getattr(config, "FETCH_THROTTLE_SECONDS", 0.5)
CLOCK_RESYNC_INTERVAL = getattr(config, "CLOCK_RESYNC_INTERVAL", 3600)

# The mutable, live ticker list — seeded once from config.TICKERS on
# first boot, then persisted to tickers.json and editable via the web
# UI from then on. config.TICKERS itself is never touched again.
tickers = web.load_tickers(getattr(config, "TICKERS", []))

quotes = {}
market_open = True  # assume open until the first market-status check
need_quotes = True  # startup: no data at all yet


def dim(color):
    return tuple(int(c * CLOSED_DIM_FACTOR) for c in color)


def all_fetches_failed():
    """True once every ticker has been attempted at least once and all of
    them came back empty — a sign the API itself is down, not just one
    bad symbol (or startup still in progress with some tickers pending)."""
    return len(quotes) == len(tickers) and all(v is None for v in quotes.values())


def fetch_and_store(symbol):
    """Fetch one ticker. Doesn't declare pass/fail here — a single
    failure mid-cycle doesn't mean the whole API is down, so that call
    is left to the display thread once every ticker's been attempted."""
    quotes[symbol] = fetch_quote(symbol)
    time.sleep(FETCH_THROTTLE_SECONDS)


def refresh_quotes():
    global market_open, need_quotes
    wifi.ensure_connected()

    if market.plausibly_open():
        # Only ask Finnhub during a window where the market could
        # actually be open — no point polling at 2am or on a Sunday.
        status = fetch_market_open()
        if status is not None:
            market_open = status  # else keep the last known state
    else:
        market_open = False

    if market_open or need_quotes:
        # Prices are moving (or this is the first fetch ever) — refresh
        # every ticker.
        for symbol in tickers:
            fetch_and_store(symbol)
        need_quotes = False
    else:
        # Closed, and we already have a baseline — don't re-fetch tickers
        # that already succeeded, but do retry ones that failed, so a
        # transient blip self-heals instead of showing "ERROR" until the
        # market reopens.
        for symbol in tickers:
            if quotes.get(symbol) is None:
                fetch_and_store(symbol)


def _render_ticker(symbol):
    if display.pu.is_pressed(display.pu.BUTTON_X):
        ip = wifi.ip_address or "NO WIFI"
        display.scroll_text("HTTP://" + ip, NEUTRAL_COLOR, speed=SCROLL_SPEED)
        return

    if display.pu.is_pressed(display.pu.BUTTON_Y):
        display.scroll_text(clock.now_string(), NEUTRAL_COLOR, speed=SCROLL_SPEED)
        return

    if symbol not in quotes:
        # Not attempted yet (startup) — nothing to show for this one
        # specifically, others may already have real data.
        display.scroll_text("PICOTICKER", NEUTRAL_COLOR, speed=SCROLL_SPEED)
        return

    quote = quotes[symbol]
    if quote is None:
        if all_fetches_failed():
            display.scroll_text("API ERROR", DOWN_COLOR, speed=SCROLL_SPEED)
        else:
            display.scroll_text(symbol + " ERROR", DOWN_COLOR, speed=SCROLL_SPEED)
    else:
        price, change_percent = quote
        color = UP_COLOR if change_percent >= 0 else DOWN_COLOR
        if not market_open:
            color = dim(color)
        display.scroll_text(format_quote(symbol, price, change_percent), color, speed=SCROLL_SPEED)


def display_loop():
    """Runs on the second core. Cycles the display from whatever's
    currently in `quotes`, entirely independent of the fetch loop's own
    timing — it never blocks on network I/O, so a slow or fully-blocked
    fetch cycle on the other core never freezes the screen. Each ticker
    starts showing real data as soon as its own first fetch lands,
    rather than waiting for the whole startup batch to finish. Holding
    the Unicorn Pack's X button shows the board's IP address instead,
    so the web UI (for editing TICKERS) is easy to find; holding Y
    shows the current time instead.

    Each ticker's render is wrapped in a try/except: an uncaught
    exception on this thread doesn't print a visible traceback the way
    a main-thread crash does — it just silently kills the thread,
    leaving the screen permanently blank with no diagnostic. Catching
    and logging here means a one-off error skips a turn instead of
    ending the whole display."""
    while True:
        for symbol in tickers:
            try:
                _render_ticker(symbol)
            except Exception as exc:
                print("display_loop error on", symbol, exc)
                time.sleep(1)


def fetch_loop():
    """Runs on the main core: keeps `quotes` fresh, resyncs the clock
    over NTP, and polls the ticker-editing web server — all three stay
    on this thread since it's the one that already safely owns the
    network stack."""
    global tickers
    server = web.start_server()

    # Sync first: refresh_quotes() (below) now checks market.plausibly_open(),
    # which reads the clock — on a cold boot that clock is still at its
    # un-synced default until this runs.
    clock.sync()
    refresh_quotes()
    last_refresh = time.ticks_ms()
    last_clock_sync = time.ticks_ms()

    while True:
        interval = config.QUOTE_REFRESH_INTERVAL if market_open else CLOSED_QUOTE_REFRESH_INTERVAL
        if time.ticks_diff(time.ticks_ms(), last_refresh) >= interval * 1000:
            refresh_quotes()
            last_refresh = time.ticks_ms()
        if time.ticks_diff(time.ticks_ms(), last_clock_sync) >= CLOCK_RESYNC_INTERVAL * 1000:
            clock.sync()
            last_clock_sync = time.ticks_ms()
        tickers = web.poll(server, tickers)
        time.sleep(1)


_thread.start_new_thread(display_loop, ())
fetch_loop()
