"""Constants for the Dawarich integration."""

from datetime import timedelta
from enum import Enum

DOMAIN = "dawarich"


DEFAULT_PORT = 80
DEFAULT_NAME = "Dawarich"
DEFAULT_SSL = False
DEFAULT_VERIFY_SSL = True
CONF_DEVICE = "mobile_app"
UPDATE_INTERVAL = timedelta(seconds=60)
VERSION_UPDATE_INTERVAL = timedelta(hours=1)


class DawarichTrackerStates(Enum):
    """States of the Dawarich tracker sensor."""

    UNKNOWN = "unknown"
    SUCCESS = "success"
    ERROR = "error"


# Dynamic High Accuracy intervals based on connected Bluetooth devices.
DEFAULT_BLUETOOTH_SENSOR = "sensor.s26ultra_bluetooth_connection"
DEFAULT_NORMAL_HIGH_ACCURACY_INTERVAL = 15
DEFAULT_CAR_HIGH_ACCURACY_INTERVAL = 7
DEFAULT_NOTIFY_SERVICE = "notify.mobile_app_s26ultra"
DEFAULT_CAR_BLUETOOTH_DEVICES = "FC:35:E6:A3:1C:32\n48:F0:7B:C4:DE:21\nE2:C0:B3:05:A3:DF"
