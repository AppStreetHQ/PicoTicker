"""Wall-clock time via NTP — the Pico has no battery-backed RTC, so
this is how it knows the time at all. MicroPython has no timezone
database, so TIMEZONE_OFFSET_HOURS is a fixed manual *standard-time*
offset from UTC; dst.load()["local"] (toggled from the web UI) adds
the extra hour on top when daylight saving is in effect, so DST
changes twice a year don't need a config.py edit and redeploy."""

import time

import ntptime

import config
import dst

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
    """Current local date and time as DD/MM/YYYY HH:MM (UK format),
    using TIMEZONE_OFFSET_HOURS plus the local DST toggle. Shown only
    on demand (holding the Y button), not cycled continuously, so it
    includes the date rather than just the time."""
    offset_hours = TIMEZONE_OFFSET_HOURS + (1 if dst.load()["local"] else 0)
    local = time.localtime(time.time() + offset_hours * 3600)
    return "{:02d}/{:02d}/{:04d} {:02d}:{:02d}".format(local[2], local[1], local[0], local[3], local[4])
