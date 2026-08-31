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
