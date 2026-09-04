"""Persisted closed-market dim level, flipped from the web UI instead
of editing config.py and redeploying — same pattern as quote_mode.py.
Stored as an integer percent of full brightness (0-100); main.py's
dim() reads this fresh on every call (like quote_mode.load()), so a
change from the web UI takes effect on the next render, no reboot
needed.

Defaults to config.CLOSED_DIM_PERCENT. Once saved here at least once,
this file — not config.py — is what's authoritative, same as
tickers.json/dst.json/quote_mode.json for their own settings."""

import json

import config

DIM_FILE = "dim_level.json"
_DEFAULT_PERCENT = getattr(config, "CLOSED_DIM_PERCENT", 15)


def load():
    try:
        with open(DIM_FILE) as f:
            percent = int(json.load(f)["percent"])
    except Exception:
        return _DEFAULT_PERCENT
    return min(100, max(0, percent))


def save(percent):
    percent = min(100, max(0, int(percent)))
    with open(DIM_FILE, "w") as f:
        json.dump({"percent": percent}, f)
