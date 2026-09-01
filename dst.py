"""Persisted daylight-saving toggles, flipped from the web UI instead
of editing config.py and redeploying — DST changes twice a year, and
a user shouldn't need to touch firmware for that. Two independent
toggles, since local time and the US market's Eastern Time don't
necessarily flip on the same dates: `local` (clock.py's display time)
and `market` (market.py's trading-hours window)."""

import json

DST_FILE = "dst.json"

_DEFAULTS = {"local": False, "market": False}


def load():
    try:
        with open(DST_FILE) as f:
            data = json.load(f)
        return {
            "local": bool(data.get("local", False)),
            "market": bool(data.get("market", False)),
        }
    except Exception:
        return dict(_DEFAULTS)


def save(local, market):
    with open(DST_FILE, "w") as f:
        json.dump({"local": bool(local), "market": bool(market)}, f)
