"""Tiny HTTP server for editing the ticker list remotely, instead of
editing config.py and redeploying. Runs polled from the fetch loop's
own thread (the one that already safely owns the network stack) —
non-blocking accept, so it never stalls fetching or the display."""

import json
import socket

TICKERS_FILE = "tickers.json"

PAGE_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<title>PicoTicker</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body {{ font-family: sans-serif; max-width: 480px; margin: 40px auto; padding: 0 16px; }}
textarea {{ width: 100%; box-sizing: border-box; font-size: 1rem; }}
button {{ font-size: 1rem; padding: 8px 16px; }}
</style>
</head>
<body>
<h1>PicoTicker</h1>
<form method="POST" action="/tickers">
<p>Symbols (comma-separated):</p>
<textarea name="tickers" rows="4">{tickers}</textarea>
<p><button type="submit">Save</button></p>
</form>
</body>
</html>"""


def load_tickers(default):
    try:
        with open(TICKERS_FILE) as f:
            return json.load(f)
    except Exception:
        save_tickers(list(default))
        return list(default)


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
    return [p.strip().upper() for p in parts if p.strip()]


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
            if new_tickers:
                tickers = new_tickers
                save_tickers(tickers)
            conn.send(b"HTTP/1.1 303 See Other\r\nLocation: /\r\n\r\n")
        else:
            page = PAGE_TEMPLATE.format(tickers=", ".join(tickers)).encode()
            conn.send(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n" + page)
    except Exception as exc:
        print("web request failed", exc)
    finally:
        conn.close()

    return tickers
