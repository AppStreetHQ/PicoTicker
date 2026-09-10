"""Tiny HTTP server for editing the ticker list remotely, instead of
editing config.py and redeploying. Runs polled from the fetch loop's
own thread (the one that already safely owns the network stack) —
non-blocking accept, so it never stalls fetching or the display."""

import json
import socket
import time

import boot_diagnostics
import config
import diagnostics_log
import dim_level
import dst
import live_quotes
import quote_mode
from stocks import symbol_exists

TICKERS_FILE = "tickers.json"
FETCH_THROTTLE_SECONDS = getattr(config, "FETCH_THROTTLE_SECONDS", 0.5)
MAX_TICKERS = 50  # Finnhub's free-tier websocket subscription limit

PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<title>PicoTicker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; }}
table {{ width: 100%; border-collapse: collapse; margin: 8px 0; }}
th, td {{ text-align: left; padding: 4px 6px; border-bottom: 1px solid #eee; }}
input[type=text] {{ font-size: 1rem; padding: 4px; }}
button {{ font-size: 1rem; padding: 8px 16px; }}
button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
.hint {{ color: #b00; min-height: 1.2em; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>PicoTicker</h1>
<h2>Watchlist</h2>
<form method="POST" action="/tickers/remove" id="removeForm">
<table>
<tr><th></th><th>Ticker</th><th>Price</th><th>Change</th></tr>
{rows}
</table>
<button type="submit" id="removeBtn" disabled>Remove selected</button>
<p class="hint">{remove_error}</p>
</form>
<script>
var removeForm = document.getElementById("removeForm");
var removeBtn = document.getElementById("removeBtn");
var checkboxes = removeForm.querySelectorAll("input[type=checkbox]");

function anyChecked() {{
    for (var i = 0; i < checkboxes.length; i++) {{
        if (checkboxes[i].checked) {{ return true; }}
    }}
    return false;
}}

for (var i = 0; i < checkboxes.length; i++) {{
    checkboxes[i].addEventListener("change", function () {{
        removeBtn.disabled = !anyChecked();
    }});
}}
removeForm.addEventListener("submit", function () {{
    removeBtn.disabled = true;
    removeBtn.textContent = "Removing...";
}});
</script>
<script>
// Polls /quotes.json to keep the table's price/change cells current
// without a full page reload — fast while streaming live off Finnhub's
// websocket, or matching config.py's QUOTE_REFRESH_INTERVAL (how often
// main.py actually re-fetches over REST) so REST mode never polls
// faster than the data itself changes.
var liveMode = {live_mode_js};
var pollInterval = liveMode ? 2000 : 60000;

function paintQuote(ticker, quote) {{
    var priceCell = document.getElementById("price-" + ticker);
    var changeCell = document.getElementById("change-" + ticker);
    if (!priceCell || !changeCell) {{ return; }}  // removed from another tab since page load
    if (!quote) {{
        priceCell.textContent = "...";
        changeCell.textContent = "...";
        changeCell.style.color = "#666";
        return;
    }}
    var price = quote[0], changePercent = quote[1];
    var sign = changePercent >= 0 ? "+" : "";
    priceCell.textContent = "$" + price.toFixed(2);
    changeCell.textContent = sign + changePercent.toFixed(2) + "%";
    changeCell.style.color = changePercent > 0 ? "#0a0" : changePercent < 0 ? "#c00" : "#666";
}}

function pollQuotes() {{
    fetch("/quotes.json?t=" + Date.now())
        .then(function (r) {{ return r.json(); }})
        .then(function (data) {{
            for (var ticker in data) {{ paintQuote(ticker, data[ticker]); }}
        }})
        .catch(function () {{}});  // a dropped request just waits for the next tick
}}

setInterval(pollQuotes, pollInterval);
</script>

{add_section}
<hr>
<h2>Daylight saving</h2>
<p>MicroPython has no timezone database, so these need flipping by
hand when your region's clocks change — no redeploy needed, just
toggle and save.</p>
<form method="POST" action="/dst" id="dstForm">
<p><label><input type="checkbox" name="local_dst" id="localDst" {local_dst_checked}> Local time is in DST (e.g. UK BST)</label></p>
<p><label><input type="checkbox" name="market_dst" id="marketDst" {market_dst_checked}> US market is in DST (EDT)</label></p>
<p><button type="submit" id="dstSave" disabled>Save</button></p>
</form>
<hr>
<h2>Price source</h2>
<p>Live prices stream in real time from Finnhub's websocket feed, but
Finnhub only allows <strong>one open connection per API key</strong> —
if more than one PicoTicker shares your key, only one should use the
websocket at a time. REST fetches on a timer instead and never
competes for that connection, so it's the safer choice if you're
running more than one device.</p>
<form method="POST" action="/quote-mode" id="quoteModeForm">
<p><label><input type="checkbox" name="live" id="liveMode" {live_checked}> Use live websocket prices</label></p>
<p><button type="submit" id="quoteModeSave" disabled>Save</button></p>
</form>
<hr>
<h2>Diagnostics</h2>
<p>{connection_status}, up {uptime}.</p>
{event_log}
<hr>
<h2>Closed-market dimming</h2>
<p>Brightness tickers are shown at while the market's closed, as a
percentage of full brightness.</p>
<form method="POST" action="/dim-level" id="dimForm">
<p><label>Dim level: <input type="number" name="percent" id="dimPercent" min="0" max="100" value="{dim_percent}"> %</label></p>
<p><button type="submit" id="dimSave" disabled>Save</button></p>
</form>
<script>
// Simple forms (no server-side validation, just enable Save once a
// field actually differs from what the page loaded with).
function trackForm(formId, buttonId, fieldIds) {{
    var form = document.getElementById(formId);
    var saveButton = document.getElementById(buttonId);
    var fields = fieldIds.map(function (id) {{ return document.getElementById(id); }});
    var initialValues = fields.map(function (el) {{
        return el.type === "checkbox" ? el.checked : el.value;
    }});

    function checkChanged() {{
        var changed = fields.some(function (el, i) {{
            var value = el.type === "checkbox" ? el.checked : el.value;
            return value !== initialValues[i];
        }});
        saveButton.disabled = !changed;
    }}

    fields.forEach(function (el) {{
        el.addEventListener("input", checkChanged);
        el.addEventListener("change", checkChanged);
    }});
    form.addEventListener("submit", function () {{
        saveButton.disabled = true;
        saveButton.textContent = "Saving...";
    }});
}}

trackForm("dstForm", "dstSave", ["localDst", "marketDst"]);
trackForm("quoteModeForm", "quoteModeSave", ["liveMode"]);
trackForm("dimForm", "dimSave", ["dimPercent"]);
</script>
</body>
</html>"""

ADD_FORM_TEMPLATE = r"""<h2>Add a stock</h2>
<form method="POST" action="/tickers/add" id="addForm">
<input type="text" name="ticker" id="newTicker" maxlength="6" placeholder="e.g. AAPL" autocapitalize="characters" value="{new_ticker_value}">
<button type="submit" id="addBtn" disabled>Add</button>
<p class="hint">{add_error}</p>
</form>
<script>
var addForm = document.getElementById("addForm");
var newTicker = document.getElementById("newTicker");
var addBtn = document.getElementById("addBtn");

function isValidSymbol(s) {{
    return s.length >= 1 && s.length <= 6 && /^[A-Za-z.]+$/.test(s);
}}

newTicker.addEventListener("input", function () {{
    addBtn.disabled = !isValidSymbol(newTicker.value.trim());
}});
addForm.addEventListener("submit", function () {{
    // Validation involves a real Finnhub lookup server-side, so the
    // round-trip can take a couple of seconds — disable immediately
    // rather than waiting for the response, so it's obvious the click landed.
    addBtn.disabled = true;
    addBtn.textContent = "Adding...";
}});
</script>"""

MAX_REACHED_TEMPLATE = r"""<h2>Add a stock</h2>
<p>You're at the {max_tickers}-ticker limit — remove one above to add another.</p>"""


def load_tickers(default):
    try:
        with open(TICKERS_FILE) as f:
            return sorted(json.load(f))
    except Exception:
        tickers = sorted(default)
        save_tickers(tickers)
        return tickers


def save_tickers(tickers):
    with open(TICKERS_FILE, "w") as f:
        json.dump(tickers, f)


def start_server(port=80):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", port))
    s.listen(1)
    s.settimeout(0)  # non-blocking accept
    return s


def _percent_decode(value):
    value = value.replace("+", " ")
    decoded = ""
    i = 0
    while i < len(value):
        if value[i] == "%" and i + 2 < len(value):
            decoded += chr(int(value[i + 1 : i + 3], 16))
            i += 3
        else:
            decoded += value[i]
            i += 1
    return decoded


def _parse_form(body):
    """Single-value form fields: last value wins on a duplicate key. Use
    _parse_multi() instead for fields that can legitimately repeat, like
    a group of same-named checkboxes."""
    fields = {}
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        fields[key] = _percent_decode(value)
    return fields


def _parse_multi(body, name):
    """All values for a repeated field name, e.g. several checkboxes
    submitted as remove=AAPL&remove=MSFT — _parse_form() would silently
    keep only the last one."""
    values = []
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        if key == name:
            values.append(_percent_decode(value))
    return values


def _validate_add(symbol, current_tickers):
    """Only ever checks the one new symbol against Finnhub — unlike the
    old bulk-textarea flow there's nothing else to re-validate. A symbol
    only blocks adding if Finnhub definitively says it doesn't exist; a
    failed lookup (API/network issue) doesn't block it, since we can't
    tell "invalid" from "Finnhub's having trouble right now"."""
    if not symbol:
        return "Enter a symbol"
    if len(symbol) > 6 or not all(c.isalpha() or c == "." for c in symbol):
        return "Invalid symbol: " + symbol
    if symbol in current_tickers:
        return symbol + " is already in your watchlist"
    if len(current_tickers) >= MAX_TICKERS:
        return "Already at the {} ticker limit".format(MAX_TICKERS)
    if symbol_exists(symbol) is False:
        return "Not a real ticker: " + symbol
    return ""


def _html_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _format_duration(seconds):
    if seconds is None:
        return "?"
    if seconds < 60:
        return "{}s".format(seconds)
    minutes = seconds // 60
    if minutes < 60:
        return "{}m {}s".format(minutes, seconds % 60)
    hours = minutes // 60
    return "{}h {}m".format(hours, minutes % 60)


def _format_quote_cells(ticker, quotes):
    """quotes holds whatever main.py's `quotes` dict currently has for
    this symbol: absent (never fetched yet), None (last fetch failed),
    or a (price, change_percent) tuple — same shape main.py's own
    display code reads (see format_quote() call site)."""
    quote = quotes.get(ticker)
    if quote is None:
        return "...", "...", "#666"
    price, change_percent = quote
    sign = "+" if change_percent >= 0 else ""
    price_text = "${:.2f}".format(price)
    change_text = "{}{:.2f}%".format(sign, change_percent)
    color = "#0a0" if change_percent > 0 else "#c00" if change_percent < 0 else "#666"
    return price_text, change_text, color


def _render_ticker_rows(tickers, quotes):
    rows = []
    for t in tickers:
        price, change, color = _format_quote_cells(t, quotes)
        rows.append(
            '<tr><td><input type="checkbox" name="remove" value="{t}"></td>'
            "<td>{t}</td>"
            '<td id="price-{t}">{price}</td>'
            '<td id="change-{t}" style="color:{color}">{change}</td></tr>'.format(
                t=t, price=price, change=change, color=color
            )
        )
    return "".join(rows)


def _quotes_json(tickers, quotes):
    """[price, change_percent] per ticker for the page's polling script
    (see /quotes.json below) — a list rather than _format_quote_cells()'s
    pre-formatted strings, so the client can recolor/format live without
    a round-trip, and null for a ticker with nothing fetched yet."""
    data = {}
    for t in tickers:
        quote = quotes.get(t)
        data[t] = None if quote is None else [quote[0], quote[1]]
    return json.dumps(data).encode()


# Anything timestamped before this is clearly an artifact of an
# unsynced clock (MicroPython's default epoch is 2021-01-01), not a
# real event time — confirmed directly on this device that a log entry
# written before the boot-time clock.sync() attempt bakes in exactly
# that, permanently showing a nonsensical "49889h ago". Callers now
# defer logging until after that attempt (see main.py), but this stays
# as a cheap backstop against any future call site that doesn't.
_MIN_PLAUSIBLE_TIMESTAMP = 1735689600  # 2025-01-01 UTC


def _event_log_html():
    """A recent-first bullet list of diagnostics_log's persisted event
    history — boot causes, stream drops (a Finnhub-initiated close
    with a reason, a stale connection, a WiFi blip, ...), and
    market-status transitions. Persisted rather than kept purely in
    memory, since the event worth diagnosing (a watchdog-triggered
    reboot) is often the very thing that would wipe an in-memory log
    clean at the moment it's most needed."""
    entries = diagnostics_log.recent()
    if not entries:
        return "<p>No events logged yet.</p>"
    now = time.time()
    items = []
    for entry in entries:
        if entry["t"] < _MIN_PLAUSIBLE_TIMESTAMP:
            when = "time unknown (logged before the clock had synced)"
        else:
            when = "{} ago".format(_format_duration(max(0, now - entry["t"])))
        items.append("<li>{}: {}</li>".format(when, _html_escape(entry["msg"])))
    return "<ul>" + "".join(items) + "</ul>"


def _render_page(tickers, quotes, remove_error="", add_error="", new_ticker_value=""):
    if len(tickers) >= MAX_TICKERS:
        add_section = MAX_REACHED_TEMPLATE.format(max_tickers=MAX_TICKERS)
    else:
        add_section = ADD_FORM_TEMPLATE.format(add_error=add_error, new_ticker_value=new_ticker_value)

    state = dst.load()
    live_mode = quote_mode.load()
    return PAGE_TEMPLATE.format(
        rows=_render_ticker_rows(tickers, quotes),
        remove_error=remove_error,
        add_section=add_section,
        live_mode_js="true" if live_mode else "false",
        local_dst_checked="checked" if state["local"] else "",
        market_dst_checked="checked" if state["market"] else "",
        live_checked="checked" if live_mode else "",
        connection_status="Live-connected" if live_quotes.connected() else "Not live-connected right now",
        uptime=_format_duration(boot_diagnostics.uptime_seconds()),
        event_log=_event_log_html(),
        dim_percent=dim_level.load(),
    ).encode()


def _recv_request(conn):
    """Read a full HTTP request. Browsers commonly send the POST body in a
    TCP segment separate from the headers, so a single recv() isn't
    guaranteed to capture it — keep reading until the header/body
    separator has arrived, then keep reading the body until it matches
    Content-Length."""
    data = b""
    while b"\r\n\r\n" not in data:
        chunk = conn.recv(2048)
        if not chunk:
            return data
        data += chunk

    header, sep, body = data.partition(b"\r\n\r\n")
    content_length = 0
    for line in header.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            content_length = int(line.split(b":", 1)[1].strip())
            break

    while len(body) < content_length:
        chunk = conn.recv(2048)
        if not chunk:
            break
        body += chunk

    return header + sep + body


def poll(server_socket, tickers, quotes=None):
    """Check for one pending request and handle it if there is one.
    Returns the (possibly updated) tickers list. Safe to call every
    loop iteration — returns immediately when nothing's waiting.
    quotes, if given, is main.py's live ticker->(price, change_percent)
    dict, used to show prices in the watchlist table — passed in rather
    than imported, to keep this module self-contained."""
    quotes = quotes if quotes is not None else {}
    try:
        conn, _ = server_socket.accept()
    except OSError:
        return tickers  # nothing pending

    try:
        # The listening socket is non-blocking (for accept()), but that
        # mode carries over to accepted connections too — recv() would
        # fail instantly with EAGAIN if the request hasn't fully
        # arrived yet. Give this one connection a real (short) blocking
        # timeout instead. Inside the try (not before it) so a failure
        # here still hits the finally below and closes the connection,
        # rather than leaking it.
        conn.settimeout(2)
        request = _recv_request(conn)
        if not request:
            return tickers
        request = request.decode()
        header, _, body = request.partition("\r\n\r\n")
        request_line = header.split("\r\n", 1)[0]
        method, path, _ = request_line.split(" ", 2)
        path = path.split("?", 1)[0]  # strip the polling script's cache-busting ?t=... param

        if method == "POST" and path == "/tickers/remove":
            to_remove = set(_parse_multi(body, "remove"))
            new_tickers = sorted(t for t in tickers if t not in to_remove)
            if not new_tickers:
                conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + _render_page(
                    tickers, quotes, remove_error="Can't remove every ticker — watchlist would be empty"
                ))
            else:
                tickers = new_tickers
                save_tickers(tickers)
                conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "POST" and path == "/tickers/add":
            fields = _parse_form(body)
            symbol = fields.get("ticker", "").strip().upper()
            error = _validate_add(symbol, tickers)
            if error:
                conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + _render_page(
                    tickers, quotes, add_error=error, new_ticker_value=symbol
                ))
            else:
                tickers = sorted(tickers + [symbol])
                save_tickers(tickers)
                conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "POST" and path == "/dst":
            # Unchecked checkboxes aren't submitted at all by the
            # browser, so presence in the form fields *is* the value.
            fields = _parse_form(body)
            dst.save("local_dst" in fields, "market_dst" in fields)
            conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "POST" and path == "/quote-mode":
            fields = _parse_form(body)
            quote_mode.save("live" in fields)
            conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "POST" and path == "/dim-level":
            fields = _parse_form(body)
            try:
                percent = int(fields.get("percent", ""))
            except ValueError:
                percent = dim_level.load()
            dim_level.save(percent)
            conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "GET" and path == "/quotes.json":
            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n\r\n" + _quotes_json(tickers, quotes))
        else:
            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n\r\n" + _render_page(tickers, quotes))
    except Exception as exc:
        print("web request failed", exc)
    finally:
        conn.close()

    return tickers
