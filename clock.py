"""Wall-clock time via NTP — the Pico has no battery-backed RTC, so
this is how it knows the time at all. MicroPython has no timezone
database, so TIMEZONE_OFFSET_HOURS is just a fixed manual offset from
UTC (no automatic daylight-saving adjustment)."""

import time

import ntptime

import config

TIMEZONE_OFFSET_HOURS = getattr(config, "TIMEZONE_OFFSET_HOURS", 0)


def sync():
    """Sync the device's clock to NTP (UTC). Safe to call repeatedly;
    on failure this just leaves whatever time was previously set."""
    try:
        ntptime.settime()
        return True
    except Exception as exc:
        print("clock sync failed", exc)
        return False


def now_string():
    """Current local time as HH:MM, using TIMEZONE_OFFSET_HOURS."""
    local = time.localtime(time.time() + TIMEZONE_OFFSET_HOURS * 3600)
    return "{:02d}:{:02d}".format(local[3], local[4])
