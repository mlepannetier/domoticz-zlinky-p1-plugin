"""
<plugin key="ZLinkyP1" name="ZLinky P1 Smart Meter" author="Community" version="1.0.2">
    <description>
        ZLinky standard-mode MQTT bridge to a Domoticz P1 Smart Meter.
    </description>
    <params>
        <param field="Mode1" label="MQTT Broker" width="200px" default="192.0.2.10"/>
        <param field="Mode2" label="MQTT Port" width="75px" default="1883"/>
        <param field="Mode3" label="MQTT Topic" width="300px" default="zigbee/YOUR_ZLINKY_DEVICE_ID"/>
    </params>
</plugin>
"""

# ZLinky P1 Smart Meter plugin for Domoticz
# Reads a Zigbee2MQTT JSON topic and updates one Domoticz P1 Smart Meter.
#
# MQTT password: fill MQTT_PASSWORD below.
# Default tariff mapping follows the ZLinky standard-mode documentation:
# EASF01 -> HC (Usage1), EASF02 -> HP (Usage2).
# Verify by observing which index increments during known HP/HC periods.

import json
import time
import threading
from queue import Queue, Empty

import Domoticz

try:
    import paho.mqtt.client as mqtt
except ImportError:
    mqtt = None


# ------------------------- Configuration -------------------------

MQTT_HOST = "192.0.2.10"
MQTT_PORT = 1883
MQTT_USERNAME = "YOUR_MQTT_USERNAME"
MQTT_PASSWORD = "PUT_YOUR_MQTT_PASSWORD_HERE"
MQTT_TOPIC = "zigbee/YOUR_ZLINKY_DEVICE_ID"
MQTT_CLIENT_ID = "domoticz-zlinky-p1"

DEVICE_NAME = "Linky ZLinky P1"
DEVICE_UNIT = 1

# Domoticz P1 expects:
# USAGE1;USAGE2;RETURN1;RETURN2;CONS;PROD
# Energy counters must be cumulative Wh integers.
#
# Use the ZLinky active_power / CCASN field when configured below.
# CCASN is averaged active power in W, not instantaneous power. The P1 CONS
# field will display this value as the active-power reading.
USE_ACTIVE_POWER_AS_CONS = True

# ZLinky standard mode / HP-HC mapping (must be validated on the installation).
HC_FIELD = "current_tier1_summ_delivered"  # EASF01, kWh
HP_FIELD = "current_tier2_summ_delivered"  # EASF02, kWh

HEARTBEAT_SECONDS = 5
RECONNECT_DELAY_SECONDS = 5

# ----------------------- End configuration -----------------------


class BasePlugin:
    def __init__(self):
        self.client = None
        self.message_queue = Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.last_payload_time = 0
        self.connected = False
        self.last_values = None
        self.last_log_time = 0

    def onStart(self):
        Domoticz.Log("ZLinky P1: starting")
        if mqtt is None:
            Domoticz.Error(
                "ZLinky P1: Python module paho-mqtt is missing. "
                "Install it in the Python environment used by Domoticz."
            )
            return

        if DEVICE_UNIT not in Devices:
            Domoticz.Device(
                Name=DEVICE_NAME,
                Unit=DEVICE_UNIT,
                Type=250,
                Subtype=1
            ).Create()

        try:
            try:
                # paho-mqtt 2.x, compatibility mode for callbacks written for 1.x
                self.client = mqtt.Client(
                    callback_api_version=mqtt.CallbackAPIVersion.VERSION1,
                    client_id=MQTT_CLIENT_ID,
                    protocol=mqtt.MQTTv311
                )
            except (AttributeError, TypeError):
                # paho-mqtt 1.x
                self.client = mqtt.Client(
                    client_id=MQTT_CLIENT_ID,
                    clean_session=True,
                    protocol=mqtt.MQTTv311
                )

            if MQTT_USERNAME:
                self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

            self.client.on_connect = self.on_mqtt_connect
            self.client.on_disconnect = self.on_mqtt_disconnect
            self.client.on_message = self.on_mqtt_message
            self.client.reconnect_delay_set(
                min_delay=RECONNECT_DELAY_SECONDS,
                max_delay=60
            )
            self.client.connect_async(MQTT_HOST, MQTT_PORT, keepalive=60)
            self.client.loop_start()
        except Exception as exc:
            Domoticz.Error("ZLinky P1: MQTT initialization failed: " + str(exc))

    def onStop(self):
        Domoticz.Log("ZLinky P1: stopping")
        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass
        self.stop_event.set()

    def onHeartbeat(self):
        # Domoticz device updates are performed here, in the plugin thread.
        latest = None
        try:
            while True:
                latest = self.message_queue.get_nowait()
        except Empty:
            pass

        if latest is None:
            return

        try:
            hc_kwh = self.as_nonnegative_number(latest.get(HC_FIELD))
            hp_kwh = self.as_nonnegative_number(latest.get(HP_FIELD))

            # kWh -> Wh integer, as required by Domoticz P1.
            usage1_hc = int(round(hc_kwh * 1000))
            usage2_hp = int(round(hp_kwh * 1000))

            if USE_ACTIVE_POWER_AS_CONS:
                # ZLinky active_power / CCASN is an averaged active-power value.
                # It is averaged active power in W, not instantaneous power.
                cons_w = int(round(self.as_nonnegative_number(
                    latest.get("active_power", 0)
                )))
            else:
                cons_w = 0

            # No production index is reported for this consumption-only setup.
            svalue = "{};{};0;0;{};0".format(
                usage1_hc, usage2_hp, cons_w
            )

            if DEVICE_UNIT in Devices:
                Devices[DEVICE_UNIT].Update(nValue=0, sValue=svalue)
                now = time.time()
                if now - self.last_log_time >= 60:
                    Domoticz.Log(
                        "ZLinky P1: updated HC={} Wh, HP={} Wh, CONS={} W "
                        "(source=active_power/CCASN, averaged W)".format(
                            usage1_hc, usage2_hp, cons_w
                        )
                    )
                    self.last_log_time = now
        except (TypeError, ValueError, OverflowError) as exc:
            Domoticz.Error("ZLinky P1: invalid MQTT values: " + str(exc))

    @staticmethod
    def as_nonnegative_number(value):
        number = float(value)
        if number < 0:
            raise ValueError("negative energy value")
        return number

    def on_mqtt_connect(self, client, userdata, flags, rc):
        if rc == 0:
            self.connected = True
            Domoticz.Log("ZLinky P1: connected to MQTT")
            client.subscribe(MQTT_TOPIC, qos=0)
        else:
            self.connected = False
            Domoticz.Error("ZLinky P1: MQTT connection refused, code {}".format(rc))

    def on_mqtt_disconnect(self, client, userdata, rc):
        self.connected = False
        if rc != 0:
            Domoticz.Log("ZLinky P1: MQTT disconnected; reconnect will be attempted")

    def on_mqtt_message(self, client, userdata, message):
        try:
            payload = json.loads(message.payload.decode("utf-8"))
            if not isinstance(payload, dict):
                return

            # Ignore partial/unusable reports instead of overwriting counters.
            if HC_FIELD not in payload or HP_FIELD not in payload:
                return

            hc = self.as_nonnegative_number(payload[HC_FIELD])
            hp = self.as_nonnegative_number(payload[HP_FIELD])
            self.as_nonnegative_number(hc)
            self.as_nonnegative_number(hp)

            # Preserve the latest complete report. Paho callback runs off-thread;
            # only queue data here and update Domoticz in onHeartbeat().
            self.message_queue.put(payload)
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
            Domoticz.Error("ZLinky P1: unable to parse MQTT message: " + str(exc))


global _plugin
_plugin = BasePlugin()


def onStart():
    _plugin.onStart()


def onStop():
    _plugin.onStop()


def onHeartbeat():
    _plugin.onHeartbeat()
