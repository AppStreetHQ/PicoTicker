# Copy this file to config.py and fill in your own values.
# config.py is gitignored — never commit real credentials.

WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"

# Free tier key from https://finnhub.io/
FINNHUB_API_KEY = "your-finnhub-api-key"

# Symbols to cycle through on the display
TICKERS = ["AAPL", "GOOGL", "MSFT", "NVDA", "RKLB", "SPCX", "QQQ"]

# Finnhub only allows one open websocket connection per API key — so if
# you're running more than one PicoTicker on the same key, only one of
# them should use live prices at a time, or they'll fight over that
# connection. This is only the *initial* setting, for a device that's
# never had its price source touched: the web UI's "Price source"
# section and Button A both flip a persisted, on-device override
# (quote_mode.json) that takes precedence over this from then on.
# Defaults to REST specifically so a freshly-flashed device never
# competes with one you've already nominated for live prices — set
# this True on the one device you actually want them on, or leave it
# False everywhere and use the web UI/Button A to choose per device.
USE_LIVE_QUOTES = False

# In live mode, prices update from the websocket, not REST polling —
# this interval just controls how often the open/closed market-status
# REST check re-runs (and, incidentally, how often the websocket
# connection is confirmed still open). In REST mode, this is the REST
# refresh interval itself. Either way, while closed, quotes aren't
# moving at all, so this doesn't apply — see CLOSED_QUOTE_REFRESH_INTERVAL
# below instead.
QUOTE_REFRESH_INTERVAL = 60

# Seconds to wait before retrying the trades websocket after it drops
# (Wi-Fi blip, Finnhub restarting the connection, etc) — a backoff so a
# persistent outage doesn't retry every second.
STREAM_RECONNECT_BACKOFF_SECONDS = 15

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

# Hours to offset NTP time (which is always UTC) by, for displaying
# local time. This is your region's *standard* (winter) offset — e.g.
# 0 for the UK (GMT), -5 for US Eastern (EST). MicroPython has no
# timezone database, so it can't auto-adjust for daylight saving; when
# your region is observing it, use the "Local time is in DST" toggle
# on the web UI instead of editing this — it adds the extra hour
# without needing a redeploy.
TIMEZONE_OFFSET_HOURS = 0

# Seconds between re-syncing the clock over NTP (the Pico has no
# battery-backed RTC, so this is how it knows the time at all).
CLOCK_RESYNC_INTERVAL = 3600

# US market ("Eastern Time") trading-hours window, in Eastern local
# time. Used to skip the Finnhub market-status check entirely outside
# plausible market hours (nights, weekends) rather than polling it
# every CLOSED_QUOTE_REFRESH_INTERVAL regardless. A symmetric 30-minute
# padding either side of the real 9:30am-4:00pm session is deliberate —
# Finnhub's own status is still what decides whether quotes actually
# refresh (and catches holidays, which this window has no way to know
# about), this just decides when it's worth asking.
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MINUTE = 0
MARKET_CLOSE_HOUR = 16
MARKET_CLOSE_MINUTE = 30

# Seconds between market-status checks while closed but still inside
# the trading-hours window above — tighter than CLOSED_QUOTE_REFRESH_INTERVAL
# so a market open (or, near the close, an early close) gets noticed
# quickly rather than waiting up to 5 minutes for the next check.
MARKET_WINDOW_REFRESH_INTERVAL = 120

# US Eastern Time's *standard* (EST, winter) offset from UTC: -5.
# Separate from TIMEZONE_OFFSET_HOURS above (your own local display
# time) since they're rarely the same place. When the US is observing
# EDT, use the "US market is in DST" toggle on the web UI rather than
# editing this — see TIMEZONE_OFFSET_HOURS above for why.
MARKET_TIMEZONE_OFFSET_HOURS = -5

# Brightness tickers are shown at while the market's closed, as a
# percentage of full brightness (0-100). This is only the *initial*
# value for a device that's never had it touched — the web UI's
# "Closed-market dimming" section flips a persisted override
# (dim_level.json) that takes precedence over this from then on, same
# as TICKERS/USE_LIVE_QUOTES above.
CLOSED_DIM_PERCENT = 30
