import time

import network

import config


def ensure_connected(attempts=5, wait_per_attempt=10):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)

    for attempt in range(attempts):
        if wlan.isconnected():
            return wlan
        print("wifi connect attempt", attempt + 1)
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        for _ in range(wait_per_attempt):
            if wlan.isconnected():
                return wlan
            time.sleep(1)
        print("  status:", wlan.status())

    return wlan
