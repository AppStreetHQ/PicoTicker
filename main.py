import time

import _thread
import machine

import boot_diagnostics
import clock
import config
import diagnostics_log
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
CLOCK_RETRY_INTERVAL = getattr(config, "CLOCK_RETRY_INTERVAL", 30)
MARKET_STATUS_RETRY_INTERVAL = getattr(config, "MARKET_STATUS_RETRY_INTERVAL", 15)
CLOSE_GRACE_SECONDS = getattr(config, "CLOSE_GRACE_SECONDS", 30)

# Hardware watchdog: a last-resort net under everything else here,
# including bugs not yet known about. If fetch_loop() ever genuinely
# hangs (a REST call blocking forever with no timeout of its own, a
# WiFi driver lockup, ...) rather than raising — which none of the
# try/except handling elsewhere in this file can do anything about,
# since nothing is raised to catch — this fires and hard-resets the
# whole chip once _feed_watchdog() stops being called for too long.
# 8000ms is close to the RP2040/2350's hardware ceiling (~8388ms;
# machine.WDT has no software-extendable timeout on this port), so
# _feed_watchdog() has to be reachable often — see its call sites for
# why each one is safe.
#
# Deliberately NOT armed here at module load: the very first WiFi
# connection can legitimately take much longer than 8s on a cold boot
# (see Known limitations in the README — occasionally the WiFi chip
# needs more real elapsed time than boot.py alone gives it), and that
# whole boot sequence runs before fetch_loop()'s main loop even starts.
# _arm_watchdog() only runs once that sequence has already completed,
# so the watchdog protects steady-state operation — where the bug it
# was added for (websocket prices silently freezing) actually
# happens — without any risk of mistaking a slow-but-normal cold boot
# for a hang and boot-looping forever.
WATCHDOG_TIMEOUT_MS = 8000
_watchdog = None


def _feed_watchdog():
    if _watchdog is not None:
        _watchdog.feed()


def _arm_watchdog():
    global _watchdog
    if _watchdog is None:
        _watchdog = machine.WDT(timeout=WATCHDOG_TIMEOUT_MS)


# Only the immediate, on-screen feedback happens this early — logging
# the boot cause (below) is deliberately deferred until after the
# boot-time clock.sync() attempt in fetch_loop(), since time.time()
# here still sits at MicroPython's un-synced default epoch
# (2021-01-01): logging it now would permanently bake a nonsensical
# "49889h ago" into this entry once the clock does sync (confirmed
# directly against this device — exactly the failure this project has
# already had to fix for market_open, applying here too).
_watchdog_recovery = machine.reset_cause() == machine.WDT_RESET
if _watchdog_recovery:
    # The RECOVERED scroll is easy to miss on a moving ticker and, once
    # missed, gone for good — logging the boot cause (once it has a
    # trustworthy timestamp) is what makes a board-level recovery
    # checkable on the web UI after the fact, the same as a
    # websocket-level drop (see live_quotes.disconnect()).
    print("recovered from a watchdog reset")
    display.scroll_text("RECOVERED", NEUTRAL_COLOR, speed=SCROLL_SPEED)

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
clock_synced = False  # True once clock.sync() has ever actually succeeded — see refresh_quotes()
market_open_confirmed = False  # True once market_open has ever been a real answer, not just the boot default — see refresh_quotes()
market_closed_since = None  # ticks_ms() of the most recent open->closed transition, or None while open — see _still_in_close_grace_period()
close_refresh_done = True  # False from the moment the market closes until the post-grace REST refresh has run once for that close


def dim(color):
    factor = dim_level.load() / 100
    return tuple(int(c * factor) for c in color)


def all_fetches_failed():
    """True once every ticker has been attempted at least once and all of
    them came back empty — a sign the API itself is down, not just one
    bad symbol (or startup still in progress with some tickers pending)."""
    return len(quotes) == len(tickers) and all(v is None for v in quotes.values())


def _still_in_close_grace_period():
    """True for CLOSE_GRACE_SECONDS after the market's most recently
    detected close. During this window the websocket is kept connected
    a little longer rather than disconnecting the instant Finnhub
    reports "closed" — a closing-auction print can take a few seconds
    to be reported after the bell, and the live feed is the most
    authoritative source available for it. Also delays the one-off
    post-close REST refresh (see refresh_quotes()) until after this
    window, so that refresh reflects Finnhub's own settled data rather
    than whatever it happened to have the instant the market closed."""
    return (
        market_closed_since is not None
        and time.ticks_diff(time.ticks_ms(), market_closed_since) < CLOSE_GRACE_SECONDS * 1000
    )


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
        _feed_watchdog()
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
    global market_open, need_quotes, market_open_confirmed, market_closed_since, close_refresh_done
    wifi.ensure_connected(feed=_feed_watchdog)

    was_open = market_open
    is_first_call = need_quotes  # captured before the need_quotes block below can clear it

    # market.plausibly_open() is a pure local-clock optimization to
    # skip asking Finnhub outside trading hours (no point polling at
    # 2am or on a Sunday) — it needs a correctly-synced clock to be
    # trustworthy at all. The REST call itself doesn't: confirmed
    # directly against this device that fetch_market_open() can
    # succeed even while clock.sync() is still failing (NTP/UDP and
    # HTTPS/TLS are unrelated network operations — one failing says
    # nothing about the other). So while unsynced, skip the
    # optimization rather than skipping the check entirely: asking
    # Finnhub directly gets a real, confirmed answer just as fast as
    # the REST call itself succeeds, instead of needlessly waiting on
    # an unrelated clock sync first.
    if clock_synced and not market.plausibly_open():
        # Outside the padded window is itself a confirmed answer, now
        # that the clock's trustworthy enough to know that — doesn't
        # need Finnhub to say so too.
        market_open = False
        market_open_confirmed = True
    else:
        status = fetch_market_open()
        if status is not None:
            market_open = status
            market_open_confirmed = True
        # else: keep the last known state — but if this is the very
        # first attempt (a transient network hiccup right after a
        # fresh boot/reset is real, not hypothetical), that "last
        # known state" is just the uninformed boot default (True),
        # displayed confidently as if it meant something.
        # market_open_confirmed staying False is what makes
        # fetch_loop() retry this much sooner than the normal interval
        # instead of leaving a possibly wrong guess on screen for a
        # while.
    if market_open != was_open:
        # A transition here should be rare and always explicable (the
        # open/close bell, or a genuine holiday) — logging it is what
        # would have caught a bad fetch_market_open() reading dimming
        # the display while the market was actually open, instead of
        # it just silently happening with nothing to point at.
        print("market_open changed:", was_open, "->", market_open)
        diagnostics_log.log("market_open changed: {} -> {}".format(was_open, market_open))
        if market_open or is_first_call:
            # Either reopened, or this is a cold boot discovering an
            # already-closed market rather than a transition observed
            # in real time (was_open's module default of True just met
            # the real, closed answer for the first time) — the
            # unconditional full fetch below (need_quotes) already
            # gets fresh REST data regardless of market state, so
            # there's nothing to catch up on and no reason to hold the
            # websocket open waiting for closing-auction trades that
            # aren't newly happening.
            market_closed_since = None
            close_refresh_done = True
        else:
            # A genuine, just-observed close. Starts the
            # CLOSE_GRACE_SECONDS window — see
            # _still_in_close_grace_period() — rather than disconnecting
            # the websocket and doing the post-close REST refresh
            # immediately: a closing-auction print can take a few
            # seconds to be reported after the bell, and cutting the
            # live feed (or asking Finnhub for a REST quote) right at
            # the instant it reports "closed" risks missing it.
            market_closed_since = time.ticks_ms()
            close_refresh_done = False

    if need_quotes:
        # First run ever — seed every ticker via REST so the display has
        # something to show immediately, regardless of open/closed. An
        # `elif` from here down: was_open's module default (True) would
        # otherwise look like a same-call "just closed" transition too
        # on a cold boot into an already-closed market, fetching every
        # ticker twice in one call.
        for symbol in tickers:
            fetch_and_store(symbol)
        need_quotes = False
    elif market_open:
        if not quote_mode.load():
            # REST mode — nothing else refreshes prices while open.
            for symbol in tickers:
                fetch_and_store(symbol)
    elif _still_in_close_grace_period():
        # Just closed, or recently closed — hold off on the
        # authoritative REST refresh a little longer (see
        # _still_in_close_grace_period()) and keep relying on the
        # still-connected (per fetch_loop()) live feed for now, in
        # case trailing settlement trades are still arriving through
        # it — the best-quality source available for them.
        pass
    elif not close_refresh_done:
        # Grace period has just elapsed — do the one-off authoritative
        # REST refresh now. Even if the live feed already caught the
        # real closing prints during the grace window, this is a cheap
        # backstop (one REST call per ticker, not recurring) against a
        # closing auction that took longer than the grace period to
        # settle, or any other staleness that crept in earlier in the
        # day for unrelated reasons.
        for symbol in tickers:
            fetch_and_store(symbol)
        close_refresh_done = True
    else:
        # Already closed, refreshed, and settled — don't re-fetch
        # tickers that already succeeded, but do retry ones that
        # failed, so a transient blip self-heals instead of showing
        # "ERROR" until the market reopens.
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
    ticker-editing web server, and feeds the hardware watchdog (see
    _feed_watchdog() above) — all five stay on this thread since it's
    the one that already safely owns the network stack."""
    global tickers, clock_sync_requested, live_toggle_requested, server, clock_synced
    server = web.start_server()

    # Sync first — needed for clock.now_string() (the Y button) and
    # for picking a sensible refresh_quotes() polling cadence below,
    # though refresh_quotes() itself no longer depends on it for
    # market_open's correctness: NTP/UDP sync and the Finnhub REST
    # calls are unrelated network operations, and asking Finnhub
    # directly works fine even before the clock's synced (confirmed
    # directly against this device). Wrapped the same as the main loop
    # below and for the same reason: a boot-time WiFi hiccup here (a
    # transient NTP failure right as WiFi comes up is a real, observed
    # failure mode) must not be able to kill this thread before the
    # loop — and its own faster retry while clock_synced is still
    # False — ever gets a chance to run.
    try:
        clock_synced = clock.sync(feed=_feed_watchdog)
        refresh_quotes()
    except Exception as exc:
        print("fetch_loop error (startup)", exc)
    # Deferred from the reset_cause check above so this entry gets a
    # trustworthy timestamp — see _watchdog_recovery's definition.
    if _watchdog_recovery:
        diagnostics_log.log("boot: recovered from a watchdog reset")
    else:
        diagnostics_log.log("boot: normal (reset_cause={})".format(machine.reset_cause()))
    _arm_watchdog()
    last_refresh = time.ticks_ms()
    last_clock_sync = time.ticks_ms()

    while True:
        try:
            if not market_open_confirmed:
                # market_open is still just an unconfirmed guess (the
                # boot default, or the last known state after a failed
                # first attempt) — retry much sooner than any of the
                # normal cadences below so a wrong guess doesn't sit on
                # screen for up to a minute.
                interval = MARKET_STATUS_RETRY_INTERVAL
            elif market_open:
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
            # While never-yet-synced, retry every CLOCK_RETRY_INTERVAL
            # (30s) rather than waiting the full CLOCK_RESYNC_INTERVAL
            # (1hr) — a failed sync used to reset that hour-long timer
            # regardless, so one transient NTP hiccup right at boot
            # could leave the clock (and therefore market_open, via
            # refresh_quotes()) wrong for up to an hour.
            resync_interval = CLOCK_RESYNC_INTERVAL if clock_synced else CLOCK_RETRY_INTERVAL
            if clock_sync_requested or time.ticks_diff(time.ticks_ms(), last_clock_sync) >= resync_interval * 1000:
                if clock.sync(feed=_feed_watchdog):
                    clock_synced = True
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
            # already in the state they're asking for. An explicit
            # switch to REST mode (quote_mode.load() False) still
            # disconnects immediately — that's what lets a second
            # PicoTicker on the same Finnhub key take over the
            # connection right away — but the market closing on its own
            # doesn't: _still_in_close_grace_period() keeps this one
            # connected a little longer first, in case trailing
            # closing-auction trades are still arriving (see
            # refresh_quotes()).
            live_mode = quote_mode.load() and (market_open or _still_in_close_grace_period())
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
        _feed_watchdog()
        time.sleep(1)


_thread.start_new_thread(display_loop, ())
fetch_loop()
