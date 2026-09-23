import time

import network
import rp2

import config

ip_address = None  # set once connected, for anything that wants to show it


def _remember_ip(wlan):
    global ip_address
    if wlan.isconnected():
        ip_address = wlan.ifconfig()[0]


def _wait_tick(feed):
    """One second of ensure_connected()'s interruptible waiting: feeds
    the watchdog if given, then reports whether BOOTSEL is being held
    (see ensure_connected()'s own note on why that's checked here)
    before sleeping the second out. Shared by the per-network
    connection wait and the between-scans wait below when nothing
    configured was in range."""
    if feed is not None:
        feed()
    if rp2.bootsel_button():
        print("BOOTSEL held - aborting wifi retries for now")
        return True
    time.sleep(1)
    return False


def ensure_connected(attempts=3, wait_per_network=10, feed=None):
    """Tries every (ssid, password) in config.WIFI_NETWORKS in priority
    order, falling through to the next one if a network isn't in range or
    the connection attempt fails - then repeats the whole list up to
    attempts times, in case a failure was transient.

    Before each attempt round, scans for currently-visible networks and
    only tries the configured ones that actually showed up, still in
    priority order - skips wlan.connect()'s own wait_per_network wait
    entirely for a network that was never going to succeed (confirmed
    directly against this project: with two networks configured and
    only the second in range, every connection attempt used to burn
    its full wait_per_network on the absent first network before ever
    trying the one actually there, which is also what made the board
    so hard to get a clean serial connection to while it was retrying).
    If the scan itself fails or comes back empty - a freshly-activated
    radio can do that - falls back to trying every configured network
    unfiltered, same as before this existed, rather than refusing to
    try at all. If nothing configured is in range this round, waits
    out wait_per_network before rescanning instead of spinning through
    every attempt near-instantly, since a network coming into range
    mid-retry (a phone hotspot switched on, say) is real - same
    BOOTSEL/watchdog-feed behaviour during that wait as a real
    connection attempt would have had.

    feed, if given, is called once a second throughout the retry
    wait — main.py passes its own watchdog-feed function here, since up
    to attempts*len(config.WIFI_NETWORKS)*wait_per_network seconds (30s by
    default for one network) of legitimate reconnection retrying would
    otherwise starve a watchdog with a hardware ceiling of ~8s.

    Also checks the Pico's physical BOOTSEL button once a second during
    that same wait, aborting all retries immediately if it's held - a
    real, if rare, situation confirmed directly against this project: at
    a location where every configured network is genuinely out of range,
    this loop can occupy the CPU persistently enough that a serial tool
    (mpremote, Thonny) rarely finds a clean moment to interrupt it,
    making even a simple config fix hard to deploy without physically
    power-cycling the board. BOOTSEL doesn't have that chicken-and-egg
    problem - it's a dedicated hardware sense pin on this chip, readable
    during normal runtime, safe to check here regardless of what else is
    running, and gives a guaranteed way to drop into an idle, trivially
    interruptible state without needing serial access to ask for it."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    for attempt in range(attempts):
        if wlan.isconnected():
            _remember_ip(wlan)
            return wlan

        try:
            visible = {result[0].decode() for result in wlan.scan()}
        except Exception as exc:
            print("wifi scan failed, trying every configured network:", exc)
            visible = None

        candidates = [
            (ssid, password)
            for ssid, password in config.WIFI_NETWORKS
            if visible is None or ssid in visible
        ]
        if visible is not None and not candidates:
            print("no configured network currently in range")

        for ssid, password in candidates:
            print("wifi connect attempt", attempt + 1, "-", ssid)
            wlan.connect(ssid, password)
            for _ in range(wait_per_network):
                if wlan.isconnected():
                    _remember_ip(wlan)
                    return wlan
                if _wait_tick(feed):
                    return wlan
            print("  status:", wlan.status())

        if not candidates:
            for _ in range(wait_per_network):
                if _wait_tick(feed):
                    return wlan

    return wlan
