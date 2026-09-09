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


def sync(attempts=3, wait_seconds=2, feed=None):
    """Sync the device's clock to NTP (UTC). Safe to call repeatedly;
    on failure this just leaves whatever time was previously set.

    Retries a few times with a short gap: confirmed against the real
    device that the very first attempt right after a fresh WiFi
    association can fail repeatedly (DNS/routing not immediately
    ready) while a manual retry moments later, network fully settled,
    succeeds on the first try. feed, if given, is called between
    attempts — main.py passes its own watchdog-feed function here,
    since the retry sleeps would otherwise risk starving it."""
    for attempt in range(attempts):
        try:
            ntptime.settime()
            return True
        except Exception as exc:
            print("clock sync attempt", attempt + 1, "failed:", exc)
            if attempt + 1 < attempts:
                if feed is not None:
                    feed()
                time.sleep(wait_seconds)
    return False


def now_string():
    """Current local date and time as DD/MM/YYYY HH:MM (UK format),
    using TIMEZONE_OFFSET_HOURS plus the local DST toggle. Shown only
    on demand (holding the Y button), not cycled continuously, so it
    includes the date rather than just the time."""
    offset_hours = TIMEZONE_OFFSET_HOURS + (1 if dst.load()["local"] else 0)
    local = time.localtime(time.time() + offset_hours * 3600)
    return "{:02d}/{:02d}/{:04d} {:02d}:{:02d}".format(local[2], local[1], local[0], local[3], local[4])
