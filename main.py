import time

import _thread

import clock
import config
import dim_level
import live_quotes
import market
import quote_mode
import web
import wifi
from display import Display
from stocks import fetch_market_open, fetch_quote, format_quote

display = Display()

UP_COLOR = (0, 200, 60)
DOWN_COLOR = (220, 30, 30)
NEUTRAL_COLOR = (200, 200, 200)
SCROLL_SPEED = getattr(config, "SCROLL_SPEED", 0.14)
CLOSED_QUOTE_REFRESH_INTERVAL = getattr(config, "CLOSED_QUOTE_REFRESH_INTERVAL", 300)
MARKET_WINDOW_REFRESH_INTERVAL = getattr(config, "MARKET_WINDOW_REFRESH_INTERVAL", 120)
FETCH_THROTTLE_SECONDS = getattr(config, "FETCH_THROTTLE_SECONDS", 0.5)
CLOCK_RESYNC_INTERVAL = getattr(config, "CLOCK_RESYNC_INTERVAL", 3600)

# The mutable, live ticker list — seeded once from config.TICKERS on
# first boot, then persisted to tickers.json and editable via the web
# UI from then on. config.TICKERS itself is never touched again.
tickers = web.load_tickers(getattr(config, "TICKERS", []))

quotes = {}
market_open = True  # assume open until the first market-status check
need_quotes = True  # startup: no data at all yet
clock_sync_requested = False  # set by the display thread, consumed by fetch_loop
live_toggle_requested = False  # set by the display thread (Button A), consumed by fetch_loop
server = None  # set once in fetch_loop(); module-level so _service_web() can reach it too


def dim(color):
    factor = dim_level.load() / 100
    return tuple(int(c * factor) for c in color)


def all_fetches_failed():
    """True once every ticker has been attempted at least once and all of
    them came back empty — a sign the API itself is down, not just one
    bad symbol (or startup still in progress with some tickers pending)."""
    return len(quotes) == len(tickers) and all(v is None for v in quotes.values())


def _service_web(seconds):
    """Keeps the web UI responsive during a slow multi-ticker REST
    operation — a refresh_quotes() pass, or live_quotes seeding
    previous-close baselines for every ticker — by polling the web
    server repeatedly across what would otherwise be one blind sleep().
    Both of those run sequentially, one REST call per ticker, on this
    same thread as the web server; without this, a POST or a page load
    would just sit there for the whole multi-ticker operation (which,
    at FETCH_THROTTLE_SECONDS alone, is several seconds before REST
    latency even factors in) instead of at most this one throttle
    wait — which is exactly the "web page goes unresponsive for a
    while" symptom this was written to fix."""
    global tickers
    deadline = time.ticks_add(time.ticks_ms(), int(seconds * 1000))
    while time.ticks_diff(deadline, time.ticks_ms()) > 0:
        new_tickers = web.poll(server, tickers)
        if new_tickers != tickers:
            # sync_tickers() is a no-op while disconnected, so this is
            # safe to call unconditionally rather than needing to know
            # whether live mode happens to be active right now.
            live_quotes.sync_tickers(new_tickers)
            tickers = new_tickers
        time.sleep_ms(50)


def fetch_and_store(symbol):
    """Fetch one ticker. Doesn't declare pass/fail here — a single
    failure mid-cycle doesn't mean the whole API is down, so that call
    is left to the display thread once every ticker's been attempted."""
    quotes[symbol] = fetch_quote(symbol)
    _service_web(FETCH_THROTTLE_SECONDS)


def refresh_quotes():
    """Refreshes market-open status, and keeps `quotes` populated via
    REST. In live mode (see quote_mode.py), the websocket stream is
    what actually keeps prices moving while the market's open — that
    connection is managed every fetch_loop() iteration, not here, so
    it reacts immediately to the market opening/closing or the price
    source being switched, rather than waiting for this function's own
    longer refresh interval. In REST mode, or whenever the market's
    closed (no trades for the websocket to report, live mode or not),
    this is the only source of truth, exactly as before live prices
    existed."""
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

    if need_quotes:
        # First run ever — seed every ticker via REST so the display has
        # something to show immediately, regardless of open/closed.
        for symbol in tickers:
            fetch_and_store(symbol)
        need_quotes = False

    if market_open:
        if not quote_mode.load():
            # REST mode — nothing else refreshes prices while open.
            for symbol in tickers:
                fetch_and_store(symbol)
    else:
        # Closed, and we already have a baseline — don't re-fetch tickers
        # that already succeeded, but do retry ones that failed, so a
        # transient blip self-heals instead of showing "ERROR" until the
        # market reopens.
        for symbol in tickers:
            if quotes.get(symbol) is None:
                fetch_and_store(symbol)


_button_a_was_pressed = False


def _check_mode_toggle_button():
    """Edge-detected, unlike the level-triggered X/Y checks below —
    Button A should flip the price source exactly once per physical
    press, not repeatedly for as long as it's held. Shows the
    resulting mode name once as immediate feedback. The actual switch
    (and, if leaving live mode, closing the websocket) happens on the
    fetch loop's thread instead — see live_toggle_requested in
    fetch_loop() — since this thread never touches the network (or,
    for the same cross-thread-safety reason, live_quotes' own state)
    directly; reading quote_mode's persisted file here is safe, since
    it's just local flash I/O, not a networked or shared-state write."""
    global _button_a_was_pressed, live_toggle_requested
    pressed = display.pu.is_pressed(display.pu.BUTTON_A)
    just_pressed = pressed and not _button_a_was_pressed
    _button_a_was_pressed = pressed
    if not just_pressed:
        return False
    live_toggle_requested = True
    label = "REST API" if quote_mode.load() else "WEBSOCKETS"
    display.scroll_text(label, NEUTRAL_COLOR, speed=SCROLL_SPEED)
    return True


def _render_ticker(symbol):
    if _check_mode_toggle_button():
        return

    if display.pu.is_pressed(display.pu.BUTTON_X):
        ip = wifi.ip_address or "NO WIFI"
        display.scroll_text("HTTP://" + ip, NEUTRAL_COLOR, speed=SCROLL_SPEED)
        return

    if display.pu.is_pressed(display.pu.BUTTON_Y):
        # This thread never touches the network itself (see
        # display_loop()'s docstring) — flag a resync for fetch_loop to
        # pick up instead of syncing here. Shows whatever's currently
        # cached this frame; a fresher reading follows within about a
        # second, in time for later frames if Y is still held.
        global clock_sync_requested
        clock_sync_requested = True
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
    shows the current time instead, and also flags a fresh NTP resync
    (this thread can't do that itself — see fetch_loop()) so drift
    since the last scheduled sync doesn't show up in the reading.
    Pressing A (a single press, not held — see
    _check_mode_toggle_button()) flips between REST and websocket
    prices, showing the new mode's name once as feedback.

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
    over NTP (both on its own schedule and on demand, whenever the
    display thread flags clock_sync_requested — see _render_ticker()),
    manages the live_quotes websocket connection (applying a pending
    live_toggle_requested from Button A, then reconciling it against
    the current quote_mode + market_open every iteration, since either
    can change between refresh_quotes() calls), and polls the
    ticker-editing web server — all four stay on this thread since it's
    the one that already safely owns the network stack."""
    global tickers, clock_sync_requested, live_toggle_requested, server
    server = web.start_server()

    # Sync first: refresh_quotes() (below) now checks market.plausibly_open(),
    # which reads the clock — on a cold boot that clock is still at its
    # un-synced default until this runs. Wrapped the same as the main
    # loop below and for the same reason: a boot-time WiFi hiccup here
    # must not be able to kill this thread before the loop (and its own
    # retry-on-the-next-interval healing) ever gets a chance to run.
    try:
        clock.sync()
        refresh_quotes()
    except Exception as exc:
        print("fetch_loop error (startup)", exc)
    last_refresh = time.ticks_ms()
    last_clock_sync = time.ticks_ms()

    while True:
        try:
            if market_open:
                interval = config.QUOTE_REFRESH_INTERVAL
            elif market.plausibly_open():
                # Closed, but within the window where it could open any
                # moment — check more eagerly than the general closed
                # cadence so the transition to open gets caught quickly.
                interval = MARKET_WINDOW_REFRESH_INTERVAL
            else:
                interval = CLOSED_QUOTE_REFRESH_INTERVAL
            if time.ticks_diff(time.ticks_ms(), last_refresh) >= interval * 1000:
                refresh_quotes()
                last_refresh = time.ticks_ms()
            if clock_sync_requested or time.ticks_diff(time.ticks_ms(), last_clock_sync) >= CLOCK_RESYNC_INTERVAL * 1000:
                clock.sync()
                clock_sync_requested = False
                last_clock_sync = time.ticks_ms()

            if live_toggle_requested:
                quote_mode.save(not quote_mode.load())
                live_toggle_requested = False

            # Reconciled every iteration (not just on refresh_quotes()'s
            # own longer timer) so both a market-open/closed transition
            # and a quote_mode change (web UI or Button A) take effect
            # within about a second, not up to QUOTE_REFRESH_INTERVAL
            # later. connect()/disconnect() are both cheap no-ops when
            # already in the state they're asking for. Closing
            # immediately on leaving live mode (rather than leaving it
            # connected until the next market check) is what lets a
            # second PicoTicker on the same Finnhub key switch to live
            # mode right away, instead of waiting for this one's
            # connection to go stale.
            live_mode = quote_mode.load() and market_open
            if live_mode:
                live_quotes.connect(tickers, poll_web=_service_web)
                live_quotes.poll(tickers, quotes, poll_web=_service_web)
            else:
                live_quotes.disconnect()

            # sync_tickers() is a no-op while disconnected, so this
            # doesn't need its own live_mode check — same reasoning as
            # _service_web() calling it unconditionally above.
            new_tickers = web.poll(server, tickers)
            if new_tickers != tickers:
                live_quotes.sync_tickers(new_tickers, poll_web=_service_web)
            tickers = new_tickers
        except Exception as exc:
            # Mirrors display_loop()'s per-ticker try/except and for the
            # same reason: an uncaught exception here doesn't print a
            # traceback the way a genuine crash does — it just silently
            # kills this whole thread, freezing quotes/market_open/the
            # web server at whatever they last were (display_loop keeps
            # running independently, showing that frozen state forever
            # with no diagnostic — e.g. still "market open" colours long
            # after the close, since nothing's updating market_open any
            # more). A WiFi hiccup or a dropped websocket mid-subscribe
            # are real, not just hypothetical — this is the same
            # never-let-one-failure-take-down-everything philosophy the
            # rest of this project already follows (see README).
            print("fetch_loop error", exc)
        time.sleep(1)


_thread.start_new_thread(display_loop, ())
fetch_loop()
