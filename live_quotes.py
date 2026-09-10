"""Real-time price updates for the open-market case, via Finnhub's
trades websocket (see finnhub_ws.py) — replaces the REST quote polling
that used to run on every refresh while the market's open. main.py's
refresh_quotes() still falls back to stocks.fetch_quote() REST calls
for the closed-market retry path, since no trades happen when the
market's shut and the stream would have nothing to report.

Each trade only carries a live price, not a % change, so this keeps
its own previous-close baseline per symbol (fetched once via REST the
first time a symbol is subscribed) and recomputes the percentage on
every trade against that cached baseline.

Module-level state, matching wifi.py/web.py's style rather than a
class — there's only ever one stream for the one Finnhub API key
("one API key can only open 1 connection at a time" per Finnhub's own
docs, so a second instance wouldn't work anyway)."""

import json
import time

import config
from finnhub_ws import WebSocket
from stocks import fetch_prev_close

FETCH_THROTTLE_SECONDS = getattr(config, "FETCH_THROTTLE_SECONDS", 0.5)
RECONNECT_BACKOFF_SECONDS = getattr(config, "STREAM_RECONNECT_BACKOFF_SECONDS", 15)
STALE_CONNECTION_SECONDS = getattr(config, "STALE_CONNECTION_SECONDS", 90)

_socket = None
_subscribed = set()
_prev_close = {}
_next_reconnect_attempt = 0
_connected_at = None  # ticks_ms() the current connection was established, or None

# Diagnostics for the web UI (see diagnostics() below) — otherwise the
# only way to see why the stream last dropped is to be watching the
# serial console at the exact moment it happens.
last_disconnect_reason = None
last_disconnect_at_ms = None
last_connection_duration_ms = None


def _seed_prev_close(symbols, poll_web=None):
    """poll_web, if given, is called instead of a blind sleep() between
    each REST call — main.py passes its own _service_web() here so the
    web UI doesn't go unresponsive for the whole seeding pass (one REST
    call per new symbol) just because it happens to run on the same
    thread as the web server."""
    for symbol in symbols:
        if symbol in _prev_close:
            continue
        prev_close = fetch_prev_close(symbol)
        if prev_close is not None:
            _prev_close[symbol] = prev_close
        if poll_web is not None:
            poll_web(FETCH_THROTTLE_SECONDS)
        else:
            time.sleep(FETCH_THROTTLE_SECONDS)


def connect(tickers, poll_web=None):
    """Open the stream and subscribe to every current ticker. Safe to
    call when already connected — does nothing."""
    global _socket, _subscribed, _connected_at
    if _socket is not None:
        return
    _seed_prev_close(tickers, poll_web)
    try:
        sock = WebSocket(config.FINNHUB_API_KEY)
        sock.connect()
        for symbol in tickers:
            sock.subscribe(symbol)
        _socket = sock
        _subscribed = set(tickers)
        _connected_at = time.ticks_ms()
    except Exception as exc:
        print("live_quotes connect failed", exc)
        _socket = None


def disconnect(reason=None):
    """Closes the stream and drops the cached previous-close baselines —
    tomorrow's reconnect must re-fetch those via REST rather than keep
    comparing against today's now-stale close. Cheap to call when
    already disconnected (main.py's fetch_loop does, every iteration
    it's not in live mode) — does nothing beyond the initial check.

    reason, if given, records this as a *diagnosed* disconnect (see
    diagnostics() below) rather than a routine one — main.py's routine
    calls (switching to REST mode, or the market simply closing) don't
    pass one, so they don't overwrite whatever the last real failure
    was with "no reason"."""
    global _socket, _subscribed, _connected_at
    global last_disconnect_reason, last_disconnect_at_ms, last_connection_duration_ms
    if _socket is None:
        return
    if reason is not None:
        last_disconnect_reason = reason
        last_disconnect_at_ms = time.ticks_ms()
        if _connected_at is not None:
            last_connection_duration_ms = time.ticks_diff(last_disconnect_at_ms, _connected_at)
    _socket.close()
    _socket = None
    _subscribed = set()
    _prev_close.clear()
    _connected_at = None


def sync_tickers(tickers, poll_web=None):
    """Subscribe newly-added tickers and unsubscribe removed ones —
    called whenever the web UI changes the ticker list. No-op while
    disconnected; connect() picks up the current list from scratch.
    If a subscribe/unsubscribe write fails (the connection dropped
    between poll() calls), disconnects rather than leaving _subscribed
    partially updated — the next poll() cycle reconnects and
    resubscribes everything fresh from the current ticker list, so
    nothing here needs its own retry logic."""
    global _subscribed
    if _socket is None:
        return
    wanted = set(tickers)
    try:
        for symbol in wanted - _subscribed:
            _seed_prev_close([symbol], poll_web)
            _socket.subscribe(symbol)
        for symbol in _subscribed - wanted:
            _socket.unsubscribe(symbol)
        _subscribed = wanted
    except Exception as exc:
        print("live_quotes sync_tickers failed", exc)
        disconnect(reason="sync_tickers: {}".format(exc))


def poll(tickers, quotes, poll_web=None):
    """Drain any pending trade messages into `quotes`. Reconnects (with
    a backoff so a persistent outage doesn't retry every second) if the
    connection has dropped, was never opened, or — deliberately a broad
    catch, not just OSError — anything about reading or parsing what
    came off the wire goes wrong. A malformed message (an unexpected
    JSON shape, a non-dict trade entry, ...) must never be able to
    raise out of here uncaught: fetch_loop() has nothing wrapping this
    call, so an uncaught exception here would silently kill the whole
    main-core thread, leaving the display frozen on stale data with no
    diagnostic — exactly the kind of failure this project's error-
    handling philosophy (see README) exists to avoid.

    poll_web is threaded through to connect() for the same reason it's
    threaded through everywhere else here: a WiFi blip drops the
    previous-close cache along with the connection (see disconnect()),
    so reconnecting after one re-seeds every ticker via REST, same as a
    fresh connect — without poll_web that would block the web server
    for the whole reseed, not just the original connect that already
    handles it.

    Separately from all that, a TCP connection can die with no error at
    all — no OSError, read() just quietly returns None forever (a NAT
    timeout or an ISP-level drop, say). That's indistinguishable from a
    connection that's merely quiet, which is exactly what happened in
    practice: prices froze for several minutes with nothing wrong
    according to any exception, needing a manual reset to clear. So
    after a successful poll, this also checks how long it's actually
    been since anything (a trade, or finnhub_ws.py's own periodic ping)
    was last received — past STALE_CONNECTION_SECONDS, it's forced
    through the same disconnect-and-backoff path as a real error,
    rather than waiting for one that may never come."""
    global _socket, _next_reconnect_attempt
    if _socket is None:
        now = time.ticks_ms()
        if time.ticks_diff(now, _next_reconnect_attempt) >= 0:
            connect(tickers, poll_web)
            if _socket is None:
                _next_reconnect_attempt = time.ticks_add(now, RECONNECT_BACKOFF_SECONDS * 1000)
        return

    try:
        messages = _socket.poll()
        for message in messages:
            _handle_message(message, quotes)
        stale_ms = time.ticks_diff(time.ticks_ms(), _socket.last_activity_ms)
        if stale_ms > STALE_CONNECTION_SECONDS * 1000:
            raise OSError("no activity for {}s, treating connection as dead".format(stale_ms // 1000))
    except Exception as exc:
        print("live_quotes stream dropped", exc)
        disconnect(reason=str(exc))
        _next_reconnect_attempt = time.ticks_add(time.ticks_ms(), RECONNECT_BACKOFF_SECONDS * 1000)


def diagnostics():
    """The most recent stream disconnect, for display on the web UI —
    otherwise the only way to see why the connection dropped is to be
    watching the serial console at the exact moment it happens."""
    seconds_ago = None
    if last_disconnect_at_ms is not None:
        seconds_ago = time.ticks_diff(time.ticks_ms(), last_disconnect_at_ms) // 1000
    duration_seconds = None if last_connection_duration_ms is None else last_connection_duration_ms // 1000
    return {
        "connected": _socket is not None,
        "reason": last_disconnect_reason,
        "seconds_ago": seconds_ago,
        "connection_duration_seconds": duration_seconds,
    }


def _handle_message(message, quotes):
    try:
        parsed = json.loads(message)
    except Exception as exc:
        print("live_quotes bad message", exc)
        return
    if parsed.get("type") != "trade":
        return
    for trade in parsed.get("data", []):
        symbol = trade.get("s")
        price = trade.get("p")
        prev_close = _prev_close.get(symbol)
        if symbol is None or price is None or not prev_close:
            continue
        change_percent = (price - prev_close) / prev_close * 100
        quotes[symbol] = (price, change_percent)
