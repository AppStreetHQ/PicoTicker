"""A small, persisted, rolling log of notable events (websocket drops,
watchdog recoveries, market-status transitions, ...) for the web UI's
diagnostics page.

Deliberately bounded (MAX_ENTRIES, oldest dropped first) rather than
kept forever, but persisted to flash rather than kept purely in
memory: the events worth diagnosing here often coincide with a full
reboot (a hardware watchdog recovery, say), which would wipe an
in-memory log clean at the exact moment it's most needed."""

import json
import time

LOG_FILE = "diagnostics_log.json"
MAX_ENTRIES = 20


def _load():
    try:
        with open(LOG_FILE) as f:
            return json.load(f)
    except Exception:
        return []


def log(message):
    entries = _load()
    entries.append({"t": time.time(), "msg": message})
    entries = entries[-MAX_ENTRIES:]
    try:
        with open(LOG_FILE, "w") as f:
            json.dump(entries, f)
    except Exception as exc:
        print("diagnostics_log write failed", exc)


def recent():
    """Most-recent-first list of {"t": epoch seconds, "msg": str}."""
    entries = _load()
    entries.reverse()
    return entries
