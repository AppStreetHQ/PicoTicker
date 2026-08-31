# PicoTicker

A Raspberry Pi Pico 2 W stock ticker, written in MicroPython. Polls live
quotes and scrolls them across a Pimoroni Pico Unicorn Pack (a 16x7 RGB LED
matrix that plugs directly onto the Pico's header — no wiring needed),
colour-coded green for up, red for down.

## Hardware

- Raspberry Pi Pico 2 W (or Pico 2 W H) — needs WiFi, so a plain Pico 2 won't work
- Pimoroni Pico Unicorn Pack, plugged directly onto the Pico's GPIO header

## Firmware

This needs **Pimoroni's own MicroPython fork** (not stock MicroPython) —
it bundles the `picounicorn` module that drives the LED matrix.

⚠️ The `v1.29.0-1` release of
[pimoroni-pico](https://github.com/pimoroni/pimoroni-pico/releases) did
**not boot on a standard Pico 2 W** (`pico2_w` and even the non-wireless
`pico2` build both hung before USB came up — a missing `MICROPY_C_HEAP_SIZE`
on these boards, per [Pimoroni's fix](https://github.com/pimoroni/pimoroni-pico/issues/1147)).
Fixed in `v1.29.0-2` — use that or later:

[`pico2_w-v1.29.0-2-pimoroni-micropython.uf2`](https://github.com/pimoroni/pimoroni-pico/releases/download/v1.29.0-2/pico2_w-v1.29.0-2-pimoroni-micropython.uf2)

To flash: hold **BOOTSEL**, plug the Pico into USB, release — it mounts as
a drive named `RP2350`. Drag the `.uf2` file onto it; it auto-ejects and
reboots into MicroPython once written.

Note: `picounicorn` exposes a class (`from picounicorn import PicoUnicorn`),
not the module-level functions shown in Pimoroni's current docs — confirmed
still true on `v1.29.0-2`, not just the older build. `display.py` here is
written against the actual API on the board.

## Setup

1. Flash the firmware above.
2. Copy `config.example.py` to `config.py` and fill in:
   - `WIFI_SSID` / `WIFI_PASSWORD`
   - `FINNHUB_API_KEY` — free tier key from [finnhub.io](https://finnhub.io/)
   - `TICKERS` — list of symbols to display, e.g. `["AAPL", "MSFT", "TSLA"]`
3. Upload `boot.py`, `main.py`, `display.py`, `font3x5.py`, `stocks.py`,
   and `config.py` to the root of the device — easiest via
   [Thonny](https://thonny.org/) ("Save as... Raspberry Pi Pico"), or
   `mpremote cp *.py :` if you have `mpremote` installed.
4. Reset the board. It connects to WiFi, then runs fetching and display on
   the RP2350's two separate cores (see Notes below) — each ticker starts
   showing real data as soon as its own first fetch lands, so the matrix
   fills in progressively rather than waiting for the whole batch.

## Project layout

```
boot.py       — runs once on power-up, connects to WiFi
main.py       — fetch_loop() on the main core, display_loop() on a second
                thread (via _thread) on the other core
wifi.py       — shared WiFi connect/retry logic, used by boot.py and main.py
display.py    — wraps picounicorn.PicoUnicorn, scrolls text across the matrix
font3x5.py    — a minimal 3x5 pixel font (digits, A-Z, $ % + - . ^)
stocks.py     — Finnhub quote fetching
config.example.py — copy to config.py and fill in secrets (gitignored)
```

## Notes

- `config.py` is gitignored since it holds your WiFi password and API key —
  never commit it.
- The display keeps scrolling through `TICKERS` continuously; quotes are
  only re-fetched from Finnhub every `QUOTE_REFRESH_INTERVAL` seconds
  (default 60), reusing cached prices in between. This keeps scrolling
  snappy and stays well under Finnhub's free-tier rate limit (60 calls/min)
  no matter how long `TICKERS` gets. While the market's closed, quotes
  aren't re-fetched at all — only the market-status check itself runs,
  every `CLOSED_QUOTE_REFRESH_INTERVAL` seconds (default 300), so the
  display keeps showing the last known prices until it reopens.
- Within a refresh cycle, each ticker's fetch is spaced out by
  `FETCH_THROTTLE_SECONDS` (default 0.5) rather than firing all of them
  back-to-back — Finnhub is Cloudflare-fronted and occasionally returns
  a plain-text rate-limit error instead of JSON under bursty requests,
  even while comfortably under the per-minute quota.
- When the market's closed (checked via Finnhub's market-status endpoint),
  quotes still show the same green/red up/down colours, just dimmed
  (`CLOSED_DIM_FACTOR` in `main.py`) rather than switched to a neutral
  colour.
- The 16x7 matrix only fits a tiny 3x5 font, so text scrolls rather than
  displaying statically.
- On this firmware, WiFi sometimes doesn't come up in time during `boot.py`
  on a cold boot, even with retries — seems to need more real elapsed time
  since power-on than `boot.py` alone gets. `wifi.ensure_connected()` is
  also called at the top of every quote refresh in `main.py`, so it
  self-heals within the first refresh cycle rather than getting stuck.
- The RP2350 has two cores, and network fetching was the only thing that
  could ever make the display freeze — `main.py` now runs `fetch_loop()`
  on the main core and `display_loop()` on a second thread (`_thread`) on
  the other core. The display thread never touches WiFi/sockets at all;
  it just reads the shared `quotes` dict and drives the LED matrix, so a
  slow or fully-blocked fetch cycle never freezes the screen. Each ticker
  shows "PICOTICKER" only until its own first fetch completes, then
  switches permanently to real data for that ticker — no need to wait
  for the whole startup batch.
