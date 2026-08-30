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

⚠️ As of writing, the current `v1.29.0-1` release of
[pimoroni-pico](https://github.com/pimoroni/pimoroni-pico/releases) does
**not boot on a standard Pico 2 W** (`pico2_w` and even the non-wireless
`pico2` build both hang before USB comes up — filed upstream, check for a
fixed release before using it). Use the older, working build instead:

[`rpi_pico2_w-v1.26.1-micropython.uf2`](https://github.com/pimoroni/pimoroni-pico-rp2350/releases/download/v1.26.1/rpi_pico2_w-v1.26.1-micropython.uf2)

To flash: hold **BOOTSEL**, plug the Pico into USB, release — it mounts as
a drive named `RP2350`. Drag the `.uf2` file onto it; it auto-ejects and
reboots into MicroPython once written.

Note: on this build, `picounicorn` exposes a class (`from picounicorn import
PicoUnicorn`), not the module-level functions shown in Pimoroni's current
docs — `display.py` here is written against the confirmed, working API.

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
4. Reset the board. It connects to WiFi, then loops through `TICKERS`,
   scrolling each quote across the matrix before moving to the next.

## Project layout

```
boot.py       — runs once on power-up, connects to WiFi
main.py       — main loop: fetch quote -> render -> repeat
display.py    — wraps picounicorn.PicoUnicorn, scrolls text across the matrix
font3x5.py    — a minimal 3x5 pixel font (digits, A-Z, $ % + - . ^)
stocks.py     — Finnhub quote fetching
config.example.py — copy to config.py and fill in secrets (gitignored)
```

## Notes

- `config.py` is gitignored since it holds your WiFi password and API key —
  never commit it.
- Finnhub's free tier is rate-limited (60 calls/min); the default poll
  interval in `config.example.py` is well under that.
- The 16x7 matrix only fits a tiny 3x5 font, so text scrolls rather than
  displaying statically.
