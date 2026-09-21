import time

import network
import rp2

import config

ip_address = None  # set once connected, for anything that wants to show it


def _remember_ip(wlan):
    global ip_address
    if wlan.isconnected():
        ip_address = wlan.ifconfig()[0]


def ensure_connected(attempts=3, wait_per_network=10, feed=None):
    """Tries every (ssid, password) in config.WIFI_NETWORKS in priority
    order, falling through to the next one if a network isn't in range or
    the connection attempt fails - then repeats the whole list up to
    attempts times, in case a failure was transient.

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
        for ssid, password in config.WIFI_NETWORKS:
            print("wifi connect attempt", attempt + 1, "-", ssid)
            wlan.connect(ssid, password)
            for _ in range(wait_per_network):
                if wlan.isconnected():
                    _remember_ip(wlan)
                    return wlan
                if rp2.bootsel_button():
                    print("BOOTSEL held - aborting wifi retries for now")
                    return wlan
                if feed is not None:
                    feed()
                time.sleep(1)
            print("  status:", wlan.status())

    return wlan
