"""Whether the US market could plausibly be open right now, judged
purely from the clock. Used to gate the actual Finnhub status check
(`stocks.fetch_market_open`) so we stop polling it altogether outside
trading hours (nights, weekends) instead of asking every
CLOSED_QUOTE_REFRESH_INTERVAL regardless. This is deliberately a
coarse local-time window with padding either side of the real
9:30am-4:00pm session — Finnhub's own answer is still what decides
whether quotes actually refresh (and is what catches holidays, which
this has no way to know about), this just decides when it's worth
asking.

MARKET_TIMEZONE_OFFSET_HOURS is Eastern Time's *standard-time* (EST)
offset from UTC, kept separate from clock.TIMEZONE_OFFSET_HOURS (your
own local display time) since they're rarely the same place.
dst.load()["market"] (toggled from the web UI) adds the extra hour on
top when the US is observing EDT, so the twice-yearly US daylight
saving change doesn't need a config.py edit and redeploy either."""

import time

import config
import dst

MARKET_TIMEZONE_OFFSET_HOURS = getattr(config, "MARKET_TIMEZONE_OFFSET_HOURS", -5)
_OPEN_MINUTES = getattr(config, "MARKET_OPEN_HOUR", 8) * 60 + getattr(config, "MARKET_OPEN_MINUTE", 30)
_CLOSE_MINUTES = getattr(config, "MARKET_CLOSE_HOUR", 16) * 60 + getattr(config, "MARKET_CLOSE_MINUTE", 30)


def plausibly_open():
    """True if it's a weekday and Eastern Time's local clock falls
    within the padded trading window."""
    offset_hours = MARKET_TIMEZONE_OFFSET_HOURS + (1 if dst.load()["market"] else 0)
    local = time.localtime(time.time() + offset_hours * 3600)
    weekday = local[6]  # 0 = Monday ... 6 = Sunday
    if weekday >= 5:
        return False
    minutes = local[3] * 60 + local[4]
    return _OPEN_MINUTES <= minutes < _CLOSE_MINUTES
