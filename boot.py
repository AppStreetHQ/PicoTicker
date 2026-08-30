import time

import wifi

time.sleep(3)  # let the WiFi chip's firmware finish loading before connecting
wlan = wifi.ensure_connected()
print("wifi connected:", wlan.isconnected(), wlan.ifconfig() if wlan.isconnected() else None)
