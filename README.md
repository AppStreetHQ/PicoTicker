# PicoTicker

A pocket-sized stock ticker built on a Raspberry Pi Pico 2 W. It scrolls
live prices across a tiny RGB LED matrix, colour-coded green for up and
red for down, and lets you edit which symbols it tracks from a web page
it hosts itself — no redeploying code just to add a ticker.

This project doubles as a fairly complete example of a "real" MicroPython
project: WiFi handling that survives flaky boot timing, a background web
server, using both of the Pico 2's cores, and talking to a live financial
API without falling over when that API (or your WiFi) misbehaves. If
you're new to MicroPython or the Pico, the [How it works](#how-it-works)
section walks through the reasoning behind those choices.

[Watch a short demo](media/demo.mp4)

## Table of contents

- [What you'll need](#what-youll-need)
- [Setup](#setup)
- [Using it](#using-it)
- [How it works](#how-it-works)
- [Project files](#project-files)
- [Known limitations](#known-limitations)

## What you'll need

**Hardware:**

- A **Raspberry Pi Pico 2 W** — specifically the **2 W**, not a plain
  Pico 2 or the original Pico W. It needs both the RP2350 chip (Pico 2)
  *and* WiFi (the "W"), and both at once — there's no combination that
  skips one and still works here. The "H" variant (pre-soldered
  headers) is the easiest to work with if you're new to this, since the
  next item plugs straight onto those header pins.
- A **[Pimoroni Pico Unicorn Pack](https://shop.pimoroni.com/products/pico-unicorn-pack)**
  — a 16×7 RGB LED matrix with four buttons, designed to plug directly
  onto a Pico-shaped board's header. No soldering or wiring needed.
- A **USB cable that supports data, not just power.** This trips people
  up a lot: many cheap or bundled micro-USB cables (especially ones
  meant for charging phones) only carry power, not data — the board
  will happily light up and draw power from one, then never show up as
  a drive or serial device, which looks exactly like a dead board or
  bad firmware but isn't. If nothing appears on your computer at all
  after flashing, trying a different cable is worth doing before
  anything else. The Pico's micro-USB port can also feel unusually
  stiff — that's normal for this board, not a sign anything's wrong —
  but use a decent-quality cable regardless, since a marginal one is a
  common source of flaky connections too.
- A **WiFi network** the board can join (2.4GHz — the Pico's WiFi chip
  doesn't do 5GHz).

**Accounts:**

- A free **[Finnhub](https://finnhub.io/)** account for an API key —
  this is what actually supplies the stock prices. The free tier
  (60 API calls/minute) is comfortably enough for a handful of tickers
  refreshing once a minute; see [How it works](#being-a-good-api-citizen)
  for how this project stays well under that limit regardless of how
  many symbols you track.

**On your computer:**

- A way to copy files onto the Pico's flash storage. This guide uses
  the serial REPL directly, but [Thonny](https://thonny.org/) (a free,
  beginner-friendly Python IDE with built-in Pico support) is the
  easiest option if this is your first time doing this — its "Save
  as... Raspberry Pi Pico" makes uploading files a simple file-save
  action.

## Setup

### 1. Flash the firmware

This board needs **Pimoroni's own MicroPython build**, not the stock
one from micropython.org — it bundles the `picounicorn` module that
drives the LED matrix, which isn't part of standard MicroPython.

Download this UF2 file:
[`pico2_w-v1.29.0-2-pimoroni-micropython.uf2`](https://github.com/pimoroni/pimoroni-pico/releases/download/v1.29.0-2/pico2_w-v1.29.0-2-pimoroni-micropython.uf2)
(or a newer release than `v1.29.0-2`, if one's since come out — see the
[pimoroni-pico releases page](https://github.com/pimoroni/pimoroni-pico/releases)).

To actually flash it:

1. Hold down the **BOOTSEL** button on the Pico, plug it into your
   computer via USB, then release the button. It should appear as a
   USB drive named `RP2350`.
2. Drag the `.uf2` file you downloaded onto that drive. It will
   auto-eject and reboot on its own once the write finishes — that's
   normal, not an error.
3. It's now running MicroPython. It won't show up as a drive anymore;
   from now on you talk to it over a serial connection (which Thonny,
   or any serial terminal, can do automatically once it's plugged in).

### 2. Get a Finnhub API key

Sign up for a free account at [finnhub.io](https://finnhub.io/) and
copy your API key from the dashboard — you'll need it in the next step.

### 3. Configure the project

In this repo, copy `config.example.py` to a new file named `config.py`
and fill in your own values:

```python
WIFI_SSID = "your-wifi-name"
WIFI_PASSWORD = "your-wifi-password"
FINNHUB_API_KEY = "your-finnhub-api-key"
TICKERS = ["AAPL", "MSFT", "TSLA"]   # starting symbols — see note below
```

`config.py` is gitignored on purpose, since it holds your WiFi password
and API key — never commit it or share it publicly. `config.example.py`
is the one that's safe to share/publish, with the rest of the tunable
settings (refresh intervals, scroll speed, etc.) documented inline.

Note on `TICKERS`: this only seeds the list the *first* time the board
boots. After that, the live list lives in a file on the device and is
edited through a web page — see [Editing your ticker list](#editing-your-ticker-list).

### 4. Upload the code

Copy every `.py` file in this repo (`boot.py`, `main.py`, `wifi.py`,
`web.py`, `display.py`, `font3x5.py`, `stocks.py`, `clock.py`,
`market.py`, `dst.py`) plus your new `config.py` onto the root of the
device's filesystem. With
Thonny, open each file and use "Save as... Raspberry Pi Pico"; with
`mpremote` installed, `mpremote cp *.py :` from this directory does it
in one go.

### 5. First boot

Reset the board (unplug/replug, or a soft reset if you're in a serial
session). Here's what happens, and what's normal:

- It connects to WiFi. This can occasionally take a little longer than
  you'd expect on the very first boot after flashing — see
  [Known limitations](#known-limitations) if it seems stuck.
- The display shows a scrolling "PICOTICKER" banner while it fetches
  your first batch of quotes. Each symbol switches over to showing its
  real price as soon as *that symbol's* fetch completes, so the matrix
  fills in gradually rather than all at once.
- Once running, it settles into its normal rhythm: cycling through your
  tickers, refreshing prices roughly once a minute.

## Using it

### Watching the ticker

Each symbol gets a turn, scrolling its price and percentage change
(green with an up-arrow if it's risen, red with a down-arrow if it's
fallen). While the market's closed, the same colours are used but
dimmed, since the numbers aren't actively moving. If a symbol fails to
fetch, it shows `SYMBOL ERROR`; if *every* symbol fails at once (a sign
Finnhub itself is having trouble, not just one bad ticker), it shows a
plain `API ERROR` instead.

### Finding the web page

Press and hold the Unicorn Pack's **X** button — the display scrolls
`HTTP://<the board's IP address>` instead of the current ticker. (This
is checked once per ticker turn, not continuously, so hold it for a
second or two rather than a quick tap.) Open that address in a browser
on the same WiFi network.

### Checking the time

Press and hold **Y** the same way to scroll the current date and time
(UK format, `DD/MM/YYYY HH:MM`, 24-hour) instead of the current
ticker — shown only while you're holding the button, not cycled
continuously, hence the date alongside the time. The board has no
battery-backed real-time clock, so it gets the time over NTP on boot
and resyncs hourly (`CLOCK_RESYNC_INTERVAL` in `config.py`), plus an
extra resync the moment you press Y — cheap RTC crystals on this
hardware can drift more than you'd expect within an hour, so holding
Y also queues up a fresh sync rather than trusting whatever the last
scheduled one left behind. The very first press after a fresh boot
still just shows whatever the clock currently has (possibly all-zero
or wrong, before the first sync completes); subsequent presses while
still held pick up the newly-synced time. There's no timezone
database on MicroPython, so `TIMEZONE_OFFSET_HOURS` in `config.py` is
a fixed *standard-time* offset from UTC — see
[Daylight saving](#daylight-saving) below for how the actual +1 hour
gets applied without a redeploy.

### Editing your ticker list

The web page shows a text box with your current symbols, comma- or
newline-separated. Edit it and hit **Save**:

- The button stays disabled until you've actually changed something
  and every symbol looks like a plausible ticker (1–6 letters/dots).
- Any symbol that's genuinely new gets checked against Finnhub's own
  symbol lookup before saving — if it doesn't recognise `XYZABC` as a
  real ticker, it'll tell you and won't save the change. This check can
  take a few seconds per new symbol (it's a live API call), so don't
  worry if "Saving..." sits there for a moment when adding several at
  once.
- Symbols are always shown and stored in alphabetical order.

### Daylight saving

The same web page has two checkboxes further down — "Local time is in
DST" and "US market is in DST" — for the two clocks this project
cares about (see [Checking the time](#checking-the-time) and
[Being a good API citizen](#being-a-good-api-citizen)). Since
MicroPython has no timezone database, it can't work out on its own
when your region's clocks change; toggle the relevant box and hit
Save, and the extra hour applies immediately, no redeploy needed.
`config.py`'s `TIMEZONE_OFFSET_HOURS` and `MARKET_TIMEZONE_OFFSET_HOURS`
only need setting once, to your region's *standard* (winter) offset —
these two toggles are the only thing that should change through the
year. The two are independent because the UK and the US don't
necessarily flip their clocks on the same date.

## How it works

This section is aimed at anyone reading the code, or curious why
certain things are built the way they are.

### Two cores, two jobs

The RP2350 chip on the Pico 2 has two CPU cores, and this project
gives each one a single, clear job:

- **The main core** runs `fetch_loop()` in `main.py` — it owns WiFi,
  fetches quotes from Finnhub, resyncs the clock over NTP, and serves
  the ticker-editing web page. All the networking lives here.
- **The second core** runs `display_loop()`, started via
  MicroPython's `_thread` module — it does nothing but read whatever
  the fetch loop has most recently stored and draw it to the LED
  matrix, on a loop, forever.

The two communicate through a couple of plain shared variables (a
dict of the latest quotes, the current ticker list, a
`clock_sync_requested` flag the display thread sets on a Y press for
the fetch loop to act on) — nothing fancier than that. The payoff:
fetching from an API is inherently unpredictable (slow DNS, a dropped
connection, Finnhub itself being briefly down — all things that
happened during development), but none of that can ever freeze the
display, because the thread driving the LEDs never touches the
network at all — even wanting a fresh clock sync has to go through
this same flag rather than calling NTP directly.

### Being a good API citizen

A few deliberate choices keep this well within Finnhub's free-tier
limits (60 calls/minute) no matter how long your ticker list gets:

- Quotes are cached and only re-fetched every `QUOTE_REFRESH_INTERVAL`
  seconds (default 60) — the display just keeps cycling through
  whatever's cached in between, rather than fetching on every scroll.
- While the market's closed, quotes aren't re-fetched *at all* — only
  a lightweight market-status check runs, on a much longer interval
  (`CLOSED_QUOTE_REFRESH_INTERVAL`, default 5 minutes). There's no
  point re-polling prices that aren't moving.
- Even that status check only runs during a padded US trading-hours
  window (`market.py`, default 8:30am-4:30pm Eastern) — outside it
  (nights, weekends), the market's assumed closed with no Finnhub call
  at all. Finnhub's own answer is still what decides whether quotes
  actually refresh (and is what catches holidays, which this window
  has no way to know about) — this just decides when it's worth
  asking. Needs `MARKET_TIMEZONE_OFFSET_HOURS` in `config.py` — Eastern
  Time's *standard* (EST) offset from UTC, separate from your own
  `TIMEZONE_OFFSET_HOURS` since they're rarely the same place; see
  [Daylight saving](#daylight-saving) for the EDT half of the year.
- Within a single refresh, each ticker's request is spaced out by
  `FETCH_THROTTLE_SECONDS` rather than firing them all back-to-back —
  Finnhub sits behind Cloudflare, which can be sensitive to bursts of
  requests even when you're nowhere near the actual per-minute quota.

### Error handling philosophy

The guiding rule: **never claim more than you actually know.** Early
versions of this project showed a generic "API down" message the
moment *any single* fetch failed — which turned out to be actively
misleading the one time it mattered, when 5 of 7 tickers failed but 2
succeeded just fine (a partial Finnhub hiccup, not an outage). Now,
that verdict is only reached once *every* ticker has actually been
attempted: a lone failure shows `SYMBOL ERROR`, and only a total wipeout
shows the broader `API ERROR`.

The same principle shows up in the ticker-validation flow: a failed
Finnhub lookup (network blip, Finnhub itself misbehaving) is treated as
*unknown*, not *invalid* — it doesn't block you from saving a ticker
that might well be perfectly real.

### The pixel font

The LED matrix is only 16 pixels wide by 7 tall, which isn't enough
room for any existing font, so `font3x5.py` defines a hand-drawn 3×5
pixel font from scratch — just enough characters for ticker symbols,
prices, and a handful of punctuation marks. At this resolution, even
single letters need real thought (the `N`, for instance, went through
three redesigns before a diagonal stroke actually read clearly at three
pixels wide).

### The web server

`web.py` is a deliberately minimal HTTP server built directly on raw
sockets — no framework, because MicroPython doesn't really have one
worth pulling in for a couple of forms. It's polled once per loop
iteration from the fetch loop (a non-blocking `accept()`, so it never
stalls fetching), handles exactly one request at a time, and keeps
the mutable ticker list (`tickers.json`) and DST toggles (`dst.json`)
on the device's flash rather than in `config.py`, which stays
reserved for one-time secrets and settings.

## Project files

```
boot.py             — runs once on power-up, connects to WiFi
main.py             — fetch_loop() on the main core, display_loop() on
                       a second thread (via _thread) on the other core
wifi.py             — WiFi connect/retry logic; also remembers the
                       board's IP once connected
web.py              — the ticker-editing web server
display.py          — wraps picounicorn.PicoUnicorn, scrolls text
font3x5.py          — the hand-drawn 3x5 pixel font
stocks.py           — Finnhub API calls (quotes, market status, symbol lookup)
clock.py            — NTP time sync and HH:MM formatting
market.py           — local-clock gate for the Finnhub market-status check
dst.py              — persisted DST toggle state, edited from the web UI
config.example.py   — copy to config.py and fill in your own secrets
tickers.json        — the live, editable ticker list (created automatically
                       on first boot; not in this repo, lives on the device)
dst.json            — the two DST toggle states (same as above — created
                       automatically, not in this repo)
media/demo.mp4      — short demo video, linked at the top of this README
```

## Known limitations

A few honest caveats, so they don't come as a surprise:

- **WiFi timing on a cold boot.** Occasionally the WiFi chip needs more
  real elapsed time after power-on than `boot.py` alone gives it, and
  the very first connection attempt fails. This self-heals within the
  first refresh cycle (the fetch loop retries the connection before
  every fetch), so it recovers on its own within roughly a minute —
  but the display will show the startup banner for a bit longer than
  usual if this happens to you.
- **The web server has no concurrent-editing protection.** If two
  people (or two browser tabs) submit changes around the same time,
  whichever request the board processes second wins, with no warning
  that the other one was overwritten. Fine for a single-household
  device sitting on your desk; not something to rely on for anything
  more.
- **`picounicorn`'s real API doesn't match Pimoroni's own docs.** Their
  published documentation shows module-level functions
  (`picounicorn.set_pixel(...)`); what's actually on the board is a
  class (`from picounicorn import PicoUnicorn`). `display.py` is
  written against what's actually there, confirmed by inspecting the
  live module on the device rather than trusting the docs.
- **If you're developing against a live board over a serial REPL:**
  once the web server's running, interrupting the fetch loop (e.g.
  Ctrl-C in Thonny) and trying to resume it directly will fail with
  `EADDRINUSE` — the port-80 socket stays bound from the interrupted
  run. A full reset (soft or hard) always clears it cleanly; that's
  the one to reach for. This doesn't affect normal use, only
  interactive development.
