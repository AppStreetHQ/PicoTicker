"""Minimal hand-rolled WebSocket client for Finnhub's real-time trades
stream (wss://ws.finnhub.io). MicroPython has no built-in websocket
client and none ships with this firmware, so this implements just
enough of RFC 6455 to talk to Finnhub specifically: the opening HTTP
upgrade handshake, masked client->server frames, and server->control
(ping/close) handling.

Two quirks of this port's ssl.wrap_socket() stream, confirmed against
the real device before relying on them here:
  - In BLOCKING mode, read(n) waits to fill the full n bytes and never
    returns short — if the peer sends fewer bytes than requested and
    then goes quiet (as happens right after the handshake response),
    it hangs forever. The handshake response length isn't known in
    advance, so it's read one byte at a time (blocking, with a real
    timeout) up to the header terminator instead of asking for a fixed
    chunk size.
  - In NON-BLOCKING mode (set via the *raw* socket's settimeout(0) —
    SSLSocket itself has no settimeout()), read(n) behaves like a
    normal POSIX non-blocking recv: it returns whatever's already
    decrypted (up to n bytes, possibly fewer), or None if nothing is
    ready yet. That's what the steady-state poll() loop relies on.
"""

import binascii
import os
import socket
import ssl

HOST = "ws.finnhub.io"
PORT = 443
CONNECT_TIMEOUT_SECONDS = 15


class WebSocket:
    def __init__(self, api_key):
        self._api_key = api_key
        self._raw = None
        self._sock = None
        self._buf = b""

    def connect(self):
        addr = socket.getaddrinfo(HOST, PORT)[0][-1]
        self._raw = socket.socket()
        self._raw.settimeout(CONNECT_TIMEOUT_SECONDS)
        self._raw.connect(addr)
        self._sock = ssl.wrap_socket(self._raw, server_hostname=HOST)
        self._handshake()
        self._raw.settimeout(0)  # non-blocking from here — see module docstring
        self._buf = b""

    def _handshake(self):
        key = binascii.b2a_base64(os.urandom(16)).strip().decode()
        request = (
            "GET /?token={} HTTP/1.1\r\n"
            "Host: {}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            "Sec-WebSocket-Key: {}\r\n"
            "Sec-WebSocket-Version: 13\r\n"
            "\r\n"
        ).format(self._api_key, HOST, key)
        self._sock.write(request.encode())

        response = b""
        while b"\r\n\r\n" not in response:
            # One byte at a time deliberately — see module docstring.
            chunk = self._sock.read(1)
            if not chunk:
                raise OSError("websocket handshake closed early")
            response += chunk
        status_line = response.split(b"\r\n", 1)[0]
        if b"101" not in status_line:
            raise OSError("websocket handshake rejected: " + str(status_line))

    def close(self):
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
        self._sock = None
        self._raw = None
        self._buf = b""

    def subscribe(self, symbol):
        self._send_text('{"type":"subscribe","symbol":"%s"}' % symbol)

    def unsubscribe(self, symbol):
        self._send_text('{"type":"unsubscribe","symbol":"%s"}' % symbol)

    def _send_text(self, text):
        self._send_frame(0x1, text.encode())

    def _send_frame(self, opcode, payload):
        length = len(payload)
        mask = os.urandom(4)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if length <= 125:
            header = bytes([0x80 | opcode, 0x80 | length])
        elif length <= 65535:
            header = bytes([0x80 | opcode, 0x80 | 126]) + length.to_bytes(2, "big")
        else:
            raise ValueError("message too large")
        self._sock.write(header + mask + masked)

    def poll(self):
        """Non-blocking: pulls in whatever new bytes are available, then
        decodes and returns a list of complete text messages found (ping
        frames are answered with a pong and never appear in the result;
        an empty list means nothing new, or nothing complete yet).
        Raises OSError if the connection has actually dropped, for the
        caller to reconnect."""
        while True:
            chunk = self._sock.read(1024)
            if chunk is None:
                break
            if chunk == b"":
                raise OSError("websocket connection closed by peer")
            self._buf += chunk

        messages = []
        while True:
            frame = self._pop_frame()
            if frame is None:
                break
            opcode, payload = frame
            if opcode == 0x9:  # ping
                self._send_frame(0xA, payload)  # pong
            elif opcode == 0x8:  # close
                raise OSError("websocket closed by server")
            elif opcode == 0x1:  # text
                messages.append(payload.decode())
        return messages

    def _pop_frame(self):
        """Pops one complete frame off the front of the receive buffer
        and returns (opcode, payload), or None if a full frame hasn't
        arrived yet. Finnhub only ever sends single-frame messages under
        64KB, so fragmented (multi-frame) messages aren't handled."""
        if len(self._buf) < 2:
            return None
        opcode = self._buf[0] & 0x0F
        length = self._buf[1] & 0x7F
        offset = 2
        if length == 126:
            if len(self._buf) < offset + 2:
                return None
            length = int.from_bytes(self._buf[offset:offset + 2], "big")
            offset += 2
        elif length == 127:
            if len(self._buf) < offset + 8:
                return None
            length = int.from_bytes(self._buf[offset:offset + 8], "big")
            offset += 8

        if len(self._buf) < offset + length:
            return None

        payload = self._buf[offset:offset + length]
        self._buf = self._buf[offset + length:]
        return opcode, payload
