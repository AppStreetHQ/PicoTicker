import time

import network

import config


def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(config.WIFI_SSID, config.WIFI_PASSWORD)
        for _ in range(20):
            if wlan.isconnected():
                break
            time.sleep(1)
    return wlan


wlan = connect_wifi()
print("wifi connected:", wlan.isconnected(), wlan.ifconfig() if wlan.isconnected() else None)
