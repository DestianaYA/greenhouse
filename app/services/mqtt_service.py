"""MQTT client wrapper (paho-mqtt 2.x).

Design notes
------------
* paho runs its own network thread (`loop_start`), so the FastAPI event loop is never blocked.
* `connect_async` + `reconnect_delay_set` give automatic reconnect with exponential backoff,
  *including* the case where the broker is down when the app boots.
* Publishing FAILS FAST when disconnected. We deliberately do not let paho queue commands
  offline: a stale "fan ON" delivered an hour later is worse than an immediate 503.
* A retained "online"/"offline" message (Last Will) on `mqtt_status_topic` lets other
  systems see whether this backend is alive.
"""
import logging
import threading
import uuid
from typing import Callable

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from app.config import Settings
from app.core.exceptions import MqttPublishError, MqttPublishTimeoutError, MqttUnavailableError

logger = logging.getLogger(__name__)

MessageHandler = Callable[[str, bytes], None]


class MqttService:
    def __init__(self, settings: Settings):
        self._settings = settings
        self._subscriptions: dict[str, tuple[int, MessageHandler]] = {}
        self._lock = threading.Lock()

        client_id = f"{settings.mqtt_client_id_prefix}-{uuid.uuid4().hex[:8]}"
        self._client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._client.will_set(settings.mqtt_status_topic, "offline", qos=1, retain=True)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        s = self._settings
        logger.info("Connecting to MQTT broker %s:%s (async, auto-reconnect)", s.mqtt_host, s.mqtt_port)
        self._client.connect_async(s.mqtt_host, s.mqtt_port, keepalive=s.mqtt_keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            if self._client.is_connected():
                # Graceful shutdown: tell subscribers we're going away (a clean disconnect
                # does NOT trigger the Last Will, so publish "offline" ourselves).
                info = self._client.publish(self._settings.mqtt_status_topic, "offline", qos=1, retain=True)
                info.wait_for_publish(timeout=2)
            self._client.disconnect()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            logger.exception("Error while disconnecting from MQTT broker")
        finally:
            self._client.loop_stop()

    @property
    def is_connected(self) -> bool:
        return self._client.is_connected()

    # ------------------------------------------------------------------ pub / sub
    def publish(self, topic: str, payload: str, qos: int, retain: bool, timeout: float) -> None:
        """Publish and (for QoS>=1) wait for the broker's acknowledgement."""
        if not self.is_connected:
            raise MqttUnavailableError()

        info = self._client.publish(topic, payload, qos=qos, retain=retain)
        if info.rc == mqtt.MQTT_ERR_NO_CONN:
            raise MqttUnavailableError()
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            raise MqttPublishError(f"Failed to publish message (paho rc={info.rc})")

        if qos > 0:
            try:
                info.wait_for_publish(timeout=timeout)
            except (ValueError, RuntimeError) as exc:
                raise MqttPublishError(str(exc)) from exc
            if not info.is_published():
                raise MqttPublishTimeoutError()
        logger.info("Published topic=%s qos=%s retain=%s", topic, qos, retain)

    def subscribe(self, topic_filter: str, handler: MessageHandler, qos: int = 1) -> None:
        """Register a handler; (re)subscribed automatically on every (re)connect."""
        with self._lock:
            self._subscriptions[topic_filter] = (qos, handler)
        self._client.message_callback_add(topic_filter, self._safe(handler))
        if self.is_connected:
            self._client.subscribe(topic_filter, qos)

    @staticmethod
    def _safe(handler: MessageHandler):
        def callback(_client, _userdata, msg):
            # An exception escaping into paho's network thread would kill the loop.
            try:
                handler(msg.topic, bytes(msg.payload))
            except Exception:  # noqa: BLE001
                logger.exception("Unhandled error in MQTT handler for topic %s", msg.topic)

        return callback

    # ------------------------------------------------------------------ callbacks
    def _on_connect(self, client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            logger.error("MQTT connection refused: %s", reason_code)
            return
        logger.info("Connected to MQTT broker")
        client.publish(self._settings.mqtt_status_topic, "online", qos=1, retain=True)
        with self._lock:
            subscriptions = list(self._subscriptions.items())
        for topic_filter, (qos, _handler) in subscriptions:
            client.subscribe(topic_filter, qos)
            logger.info("Subscribed to %s (qos=%s)", topic_filter, qos)

    def _on_disconnect(self, _client, _userdata, _flags, reason_code, _properties):
        if reason_code.is_failure:
            logger.warning("MQTT connection lost (%s); paho will retry automatically", reason_code)
        else:
            logger.info("Disconnected from MQTT broker")
