"""Tracks how long the current boot has been running, for display on
the web UI's diagnostics page — see diagnostics_log.py for the
persisted, cross-reboot event history (boot causes, stream drops,
market-status transitions)."""

import time

_boot_ms = time.ticks_ms()


def uptime_seconds():
    return time.ticks_diff(time.ticks_ms(), _boot_ms) // 1000
