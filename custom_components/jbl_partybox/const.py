"""Constants for the JBL PartyBox integration."""

from datetime import timedelta

DOMAIN = "jbl_partybox"
MANUFACTURER = "JBL"

CONF_MAC = "mac"
"""Classic Bluetooth MAC from the advertisement; the BLE address rotates."""
CONF_MODEL = "model"
CONF_STAY_CONNECTED = "stay_connected"

REFRESH_INTERVAL = timedelta(minutes=5)
"""How often to read the full state while the speaker is on."""
RETRY_INTERVAL = timedelta(seconds=30)
"""Retry delay after a failed read while the speaker is on."""
UNAVAILABLE_AFTER = timedelta(minutes=5)
"""Mark the speaker unavailable when no advertisement arrived for this long."""
POWER_GRACE = 15.0
"""Seconds to trust a power command over the (lagging) advertisement."""

SERVICE_DJ_EFFECT = "dj_effect"
ATTR_CONFIG_ENTRY_ID = "config_entry_id"
ATTR_EFFECT = "effect"
ATTR_LEVEL = "level"
ATTR_DURATION = "duration"
