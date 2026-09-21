"""Persisted set of tickers *excluded* from ticker (scroll) mode's
cycle, edited per-row from the web UI's watchlist checkboxes. Heatmap
mode (see config.DISPLAY_MODE) always shows every watchlist ticker
regardless of this — it only narrows what ticker mode cycles through,
for a watchlist too long to sit through one symbol at a time.

Storing exclusions rather than inclusions means a missing/empty file
means "show everything", matching scroll mode's original behaviour
with no migration needed for an existing device."""

import json

SELECTION_FILE = "scroll_selection.json"


def load():
    try:
        with open(SELECTION_FILE) as f:
            return set(json.load(f))
    except Exception:
        return set()


def save(excluded):
    with open(SELECTION_FILE, "w") as f:
        json.dump(sorted(excluded), f)
