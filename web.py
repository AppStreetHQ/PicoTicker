"""Tiny HTTP server for editing the ticker list remotely, instead of
editing config.py and redeploying. Runs polled from the fetch loop's
own thread (the one that already safely owns the network stack) —
non-blocking accept, so it never stalls fetching or the display."""

import json
import socket
import time

import config
import dst
from stocks import symbol_exists

TICKERS_FILE = "tickers.json"
FETCH_THROTTLE_SECONDS = getattr(config, "FETCH_THROTTLE_SECONDS", 0.5)

PAGE_TEMPLATE = r"""<!DOCTYPE html>
<html>
<head>
<title>PicoTicker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; }}
textarea {{ width: 100%; box-sizing: border-box; font-size: 1rem; }}
button {{ font-size: 1rem; padding: 8px 16px; }}
button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
#hint {{ color: #b00; min-height: 1.2em; font-size: 0.9rem; }}
</style>
</head>
<body>
<h1>PicoTicker</h1>
<form method="POST" action="/tickers" id="tickerForm">
<p>Symbols (comma-separated):</p>
<textarea name="tickers" id="tickers" rows="4">{tickers}</textarea>
<p id="hint">{error}</p>
<p><button type="submit" id="save" disabled>Save</button></p>
</form>
<hr>
<h2>Daylight saving</h2>
<p>MicroPython has no timezone database, so these need flipping by
hand when your region's clocks change — no redeploy needed, just
toggle and save.</p>
<form method="POST" action="/dst">
<p><label><input type="checkbox" name="local_dst" {local_dst_checked}> Local time is in DST (e.g. UK BST)</label></p>
<p><label><input type="checkbox" name="market_dst" {market_dst_checked}> US market is in DST (EDT)</label></p>
<p><button type="submit">Save</button></p>
</form>
<script>
var form = document.getElementById("tickerForm");
var textarea = document.getElementById("tickers");
var button = document.getElementById("save");
var hint = document.getElementById("hint");
var initial = textarea.value;

form.addEventListener("submit", function () {{
    // Validation may involve real Finnhub lookups server-side, so the
    // round-trip can take a few seconds — disable immediately rather
    // than waiting for the response, so it's obvious the click landed.
    button.disabled = true;
    button.textContent = "Saving...";
    hint.textContent = "";
}});

function isValidSymbol(s) {{
    return s.length >= 1 && s.length <= 6 && /^[A-Za-z.]+$/.test(s);
}}

function validate(value) {{
    var parts = value.replace(/\r/g, ",").replace(/\n/g, ",").split(",");
    var count = 0;
    for (var i = 0; i < parts.length; i++) {{
        var s = parts[i].trim();
        if (s.length === 0) {{ continue; }}
        if (!isValidSymbol(s)) {{ return "Invalid symbol: " + s; }}
        count++;
    }}
    if (count === 0) {{ return "Enter at least one symbol"; }}
    return "";
}}

textarea.addEventListener("input", function () {{
    var changed = textarea.value !== initial;
    var error = validate(textarea.value);
    hint.textContent = changed ? error : "";
    button.disabled = !changed || error !== "";
}});
</script>
</body>
</html>"""


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
    fields = {}
    for pair in body.split("&"):
        if "=" not in pair:
            continue
        key, _, value = pair.partition("=")
        fields[key] = _percent_decode(value)
    return fields


def _parse_tickers_field(raw):
    parts = raw.replace("\r", ",").replace("\n", ",").split(",")
    return sorted(p.strip().upper() for p in parts if p.strip())


def _validation_error(new_tickers, current_tickers):
    """Check any symbols that weren't already saved before — no point
    re-checking ones already confirmed valid. Returns an error message
    string, or "" if the submission is fine to save. A symbol only
    blocks saving if Finnhub definitively says it doesn't exist; a
    failed lookup (API/network issue) doesn't block it, since we can't
    tell "invalid" from "Finnhub's having trouble right now"."""
    if not new_tickers:
        return "Enter at least one symbol"

    unknown = [t for t in new_tickers if t not in current_tickers]
    bad = []
    for symbol in unknown:
        if symbol_exists(symbol) is False:
            bad.append(symbol)
        time.sleep(FETCH_THROTTLE_SECONDS)

    if bad:
        return "Not a real ticker: " + ", ".join(bad)
    return ""


def _render_page(tickers, error):
    state = dst.load()
    return PAGE_TEMPLATE.format(
        tickers=", ".join(tickers),
        error=error,
        local_dst_checked="checked" if state["local"] else "",
        market_dst_checked="checked" if state["market"] else "",
    ).encode()


def poll(server_socket, tickers):
    """Check for one pending request and handle it if there is one.
    Returns the (possibly updated) tickers list. Safe to call every
    loop iteration — returns immediately when nothing's waiting."""
    try:
        conn, _ = server_socket.accept()
    except OSError:
        return tickers  # nothing pending

    # The listening socket is non-blocking (for accept()), but that mode
    # carries over to accepted connections too — recv() would fail
    # instantly with EAGAIN if the request hasn't fully arrived yet.
    # Give this one connection a real (short) blocking timeout instead.
    conn.settimeout(2)

    try:
        request = conn.recv(2048)
        if not request:
            return tickers
        request = request.decode()
        header, _, body = request.partition("\r\n\r\n")
        request_line = header.split("\r\n", 1)[0]
        method, path, _ = request_line.split(" ", 2)

        if method == "POST" and path == "/tickers":
            fields = _parse_form(body)
            new_tickers = _parse_tickers_field(fields.get("tickers", ""))
            error = _validation_error(new_tickers, tickers)
            if error:
                conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + _render_page(new_tickers, error))
            else:
                tickers = new_tickers
                save_tickers(tickers)
                conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        elif method == "POST" and path == "/dst":
            # Unchecked checkboxes aren't submitted at all by the
            # browser, so presence in the form fields *is* the value.
            fields = _parse_form(body)
            dst.save("local_dst" in fields, "market_dst" in fields)
            conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        else:
            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + _render_page(tickers, ""))
    except Exception as exc:
        print("web request failed", exc)
    finally:
        conn.close()

    return tickers
