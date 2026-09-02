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

_socket = None
_subscribed = set()
_prev_close = {}
_next_reconnect_attempt = 0


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
    global _socket, _subscribed
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
    except Exception as exc:
        print("live_quotes connect failed", exc)
        _socket = None


def disconnect():
    """Closes the stream and drops the cached previous-close baselines —
    tomorrow's reconnect must re-fetch those via REST rather than keep
    comparing against today's now-stale close. Cheap to call when
    already disconnected (main.py's fetch_loop does, every iteration
    it's not in live mode) — does nothing beyond the initial check."""
    global _socket, _subscribed
    if _socket is None:
        return
    _socket.close()
    _socket = None
    _subscribed = set()
    _prev_close.clear()


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
        disconnect()


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
    handles it."""
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
    except Exception as exc:
        print("live_quotes stream dropped", exc)
        disconnect()
        _next_reconnect_attempt = time.ticks_add(time.ticks_ms(), RECONNECT_BACKOFF_SECONDS * 1000)


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
