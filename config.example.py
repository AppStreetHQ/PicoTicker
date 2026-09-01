# Copy this file to config.py and fill in your own values.
# config.py is gitignored — never commit real credentials.

WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

# Free tier key from https://finnhub.io/
FINNHUB_API_KEY = "your-finnhub-api-key"

# Symbols to cycle through on the display
TICKERS = ["AAPL", "GOOGL", "MSFT", "NVDA", "RKLB", "SPCX", "QQQ"]

# Seconds between re-fetching quotes from Finnhub. The display keeps
# scrolling through TICKERS continuously between refreshes, reusing the
# last-fetched prices — this is what keeps you under Finnhub's free-tier
# rate limit (60 calls/min) regardless of how long TICKERS gets.
QUOTE_REFRESH_INTERVAL = 60

# Seconds to wait between each ticker's fetch within a single refresh
# cycle. Without this, fetching a long TICKERS list fires every request
# back-to-back with no gap, which risks tripping Finnhub's Cloudflare-
# fronted rate limiting even while staying under the per-minute quota.
FETCH_THROTTLE_SECONDS = 0.5

# Seconds between market-status checks while the market is closed. Quotes
# themselves aren't re-fetched at all while closed (prices aren't moving) —
# this just controls how often we check whether it's reopened.
CLOSED_QUOTE_REFRESH_INTERVAL = 300

# Seconds per column-shift while scrolling text — lower is faster.
SCROLL_SPEED = 0.13

# Seconds between re-syncing the clock over NTP (the Pico has no
# battery-backed RTC, so this is how it knows the time at all).
CLOCK_RESYNC_INTERVAL = 3600

# US market ("Eastern Time") trading-hours window, in Eastern local
# time. Used to skip the Finnhub market-status check entirely outside
# plausible market hours (nights, weekends) rather than polling it
# every CLOSED_QUOTE_REFRESH_INTERVAL regardless. The padding either
# side of the real 9:30am-4:00pm session is deliberate — Finnhub's own
# status is still what decides whether quotes actually refresh (and
# catches holidays, which this window has no way to know about), this
# just decides when it's worth asking.
MARKET_OPEN_HOUR = 8
MARKET_OPEN_MINUTE = 30
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 30

# US Eastern Time's *standard* (EST, winter) offset from UTC: -5. This
# is the anchor everything else (including TIMEZONE_OFFSET_FROM_MARKET_HOURS
# below) is built from. When the US is observing EDT, use the "US
# market is in DST" toggle on the web UI rather than editing this.
MARKET_TIMEZONE_OFFSET_HOURS = -5

# Your local standard-time offset *relative to the market's own
# standard time* (Eastern Standard Time), not from UTC. This is a
# fixed geographic relationship that (almost) never changes, unlike
# an absolute UTC offset which needs revisiting every time either
# side's daylight saving flips. E.g. the UK is 5 hours ahead of EST
# (GMT vs EST), so a UK user sets 5; someone in the market's own zone
# (US Eastern) sets 0; US Pacific is 3 hours behind, so -3. When your
# own region is observing daylight saving, use the "Local time is in
# DST" toggle on the web UI instead of editing this — it adds the
# extra hour on your side independently of the market's own DST state.
TIMEZONE_OFFSET_FROM_MARKET_HOURS = 0
