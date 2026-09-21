"""Persisted ticker-vs-heatmap display mode, flipped from Button B
instead of editing config.py and redeploying.

Defaults to config.DISPLAY_MODE (itself defaulting to "scroll") until
first saved here — once saved, this file, not config.py, is what's
authoritative, same relationship quote_mode.json/dim_level.json have
with their own config.py defaults."""

import json

import config

MODE_FILE = "display_mode.json"
_DEFAULT_MODE = getattr(config, "DISPLAY_MODE", "scroll")


def load():
    try:
        with open(MODE_FILE) as f:
            return json.load(f)["mode"]
    except Exception:
        return _DEFAULT_MODE


def save(mode):
    with open(MODE_FILE, "w") as f:
        json.dump({"mode": mode}, f)
