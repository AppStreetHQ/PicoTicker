"""Persisted live-vs-REST quote source, flipped from the web UI or
Button A instead of editing config.py and redeploying — the single
source of truth both of those write to and main.py reads every
fetch_loop() iteration.

Defaults to REST (config.USE_LIVE_QUOTES, itself defaulting to False)
so that multiple PicoTickers sharing one Finnhub API key don't fight
over its single websocket connection slot out of the box — nominate
the one device you actually want live prices on by flipping this,
either in that device's own config.py or at runtime. Once saved here
at least once, this file — not config.py — is what's authoritative,
same as tickers.json/dst.json for their own settings."""

import json

import config

MODE_FILE = "quote_mode.json"
_DEFAULT_LIVE = getattr(config, "USE_LIVE_QUOTES", False)


def load():
    try:
        with open(MODE_FILE) as f:
            return bool(json.load(f)["live"])
    except Exception:
        return _DEFAULT_LIVE


def save(live):
    with open(MODE_FILE, "w") as f:
        json.dump({"live": bool(live)}, f)
