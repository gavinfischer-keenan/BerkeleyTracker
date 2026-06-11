"""MQTT publisher for BerkeleyTracker — standard agent lifecycle."""
from __future__ import annotations

import json
import time

import paho.mqtt.client as mqtt
import structlog

log = structlog.get_logger(__name__)

TOPIC_STATUS = "home/status/tracker"


class MqttTrackerPublisher:
    def __init__(self, broker: str = "localhost", port: int = 1883) -> None:
        self.broker = broker
        self.port = port
        self._client = mqtt.Client(client_id="berkeley-tracker", protocol=mqtt.MQTTv311)
        self._connected = False
        self._client.will_set(
            TOPIC_STATUS,
            json.dumps({"status": "offline", "agent": "tracker"}),
            qos=1, retain=True,
        )

    def start(self) -> None:
        self._client.connect(self.broker, self.port, keepalive=60)
        self._client.loop_start()
        self._connected = True
        self._publish(TOPIC_STATUS, {
            "status": "online",
            "agent": "tracker",
            "version": "0.1.0",
            "timestamp": int(time.time() * 1000),
        }, qos=1, retain=True)
        log.info("mqtt_publisher.started", broker=self.broker)

    def stop(self) -> None:
        self._publish(TOPIC_STATUS, {
            "status": "offline",
            "agent": "tracker",
            "timestamp": int(time.time() * 1000),
        }, qos=1, retain=True)
        self._client.loop_stop()
        self._client.disconnect()
        self._connected = False
        log.info("mqtt_publisher.stopped")

    def _publish(self, topic: str, payload: dict, qos: int = 1, retain: bool = False) -> None:
        if not self._connected:
            return
        self._client.publish(topic, json.dumps(payload, default=str), qos=qos, retain=retain)

    def publish_aircraft_seen(self, icao_hex: str, data: dict) -> None:
        self._publish("home/events/tracker/aircraft-seen", {
            "icao": icao_hex, **data, "timestamp": int(time.time() * 1000),
        })

    def publish_vessel_seen(self, mmsi: str, data: dict) -> None:
        self._publish("home/events/tracker/vessel-seen", {
            "mmsi": mmsi, **data, "timestamp": int(time.time() * 1000),
        })

    def publish_new_craft(self, craft_type: str, craft_id: str, data: dict) -> None:
        topic = f"home/events/tracker/{craft_type}-new"
        self._publish(topic, {
            "craft_type": craft_type, "craft_id": craft_id,
            **data, "timestamp": int(time.time() * 1000),
        })

    def publish_route_learned(self, route_data: dict) -> None:
        self._publish("home/events/tracker/route-learned", {
            **route_data, "timestamp": int(time.time() * 1000),
        })

    def publish_notable(self, craft_type: str, craft_id: str,
                        reason: str, data: dict) -> None:
        self._publish("home/events/tracker/notable", {
            "craft_type": craft_type, "craft_id": craft_id,
            "reason": reason, **data, "timestamp": int(time.time() * 1000),
        })

    def publish_stats(self, adsb_stats: dict, ais_stats: dict) -> None:
        self._publish("home/sensors/tracker/adsb-stats", adsb_stats, qos=0)
        self._publish("home/sensors/tracker/ais-stats", ais_stats, qos=0)
