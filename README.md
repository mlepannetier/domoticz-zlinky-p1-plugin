# Domoticz ZLinky P1 plugin

A Domoticz Python plugin that reads ZLinky standard-mode measurements from a Zigbee2MQTT MQTT JSON topic and publishes them as a separate Domoticz P1 Smart Meter device.

**Version:** 1.0.2

## Features

- Reads cumulative HC/HP energy counters from a ZLinky MQTT JSON payload.
- Converts energy values from kWh to integer Wh, as expected by the Domoticz P1 device format.
- Creates a separate Domoticz P1 device; it does not modify existing devices or migrate their history.
- Uses the `active_power` payload field for the P1 `CONS` field. This value may represent CCASN/averaged active power, not instantaneous power.
- Ignores partial payloads that do not contain both energy counters.

## MQTT payload fields

The default mapping in `plugin.py` is:

| Domoticz field | MQTT JSON field | Meaning |
| --- | --- | --- |
| `USAGE1` | `current_tier1_summ_delivered` | HC / EASF01, kWh converted to Wh |
| `USAGE2` | `current_tier2_summ_delivered` | HP / EASF02, kWh converted to Wh |
| `CONS` | `active_power` | Power in W, rounded to an integer |

The HC/HP mapping must be verified against the tariff periods of the installation. If the indexes increase in the opposite periods, change the mapping only after validating the payload.

## Configuration

Edit the configuration constants near the top of `zlinky_p1/plugin.py`:

```python
MQTT_HOST = "192.0.2.10"  # Replace with your MQTT broker address
MQTT_PORT = 1883
MQTT_USERNAME = "YOUR_MQTT_USERNAME"
MQTT_PASSWORD = "PUT_YOUR_MQTT_PASSWORD_HERE"
MQTT_TOPIC = "zigbee/YOUR_ZLINKY_DEVICE_ID"
```

`192.0.2.10` is a documentation-only example address, not a usable broker address. Replace it and the username, password, and topic with your own values. Do not commit credentials, local IP addresses, device IEEE addresses, or other installation-specific identifiers to a public repository.

The plugin definition also contains MQTT broker and topic defaults for the Domoticz hardware list. These defaults are examples; the runtime configuration is defined by the constants above.

## Requirements

- Domoticz with Python plugin support enabled.
- Python package `paho-mqtt` installed in the Python environment used by Domoticz.
- A reachable MQTT broker publishing ZLinky standard-mode JSON messages.

## Installation

1. Back up your Domoticz configuration.
2. Copy the `zlinky_p1` directory into the Domoticz plugins directory.
3. Edit the MQTT constants in `zlinky_p1/plugin.py` for your installation.
4. Ensure `paho-mqtt` is available to Domoticz's Python runtime.
5. Restart Domoticz.
6. In **Setup → Hardware**, add the **ZLinky P1 Smart Meter** Python plugin.
7. Check the Domoticz log for `ZLinky P1: connected to MQTT`.
8. Confirm the created device's HC/HP counters against the source payload and validate the mapping during known HC and HP periods.

## Notes

- The plugin creates a separate device named `Linky ZLinky P1` (unit 1 in the plugin).
- Existing Domoticz devices and historical data are not changed.
- Historical graphs start accumulating after the plugin begins updating the new device; this plugin does not copy old history.
- The plugin uses plain MQTT on port 1883 by default. Do not expose an unauthenticated or untrusted MQTT broker to the Internet.

## Repository contents

```text
.
├── README.md
├── .gitignore
└── zlinky_p1/
    └── plugin.py
```
