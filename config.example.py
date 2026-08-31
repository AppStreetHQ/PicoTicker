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

# Seconds between refreshes while the market is closed — prices aren't
# moving, so there's no need to poll as often.
CLOSED_QUOTE_REFRESH_INTERVAL = 300

# Seconds per column-shift while scrolling text — lower is faster.
SCROLL_SPEED = 0.13
