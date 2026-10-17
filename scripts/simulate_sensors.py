"""Simulate greenhouse sensors publishing readings over MQTT.

    python scripts/simulate_sensors.py --host localhost --sensors 3 --interval 2

Publishes JSON to greenhouse/sensor/{sensor_id}; the backend stores each message.
"""
import argparse
import json
import random
import time

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--sensors", type=int, default=3)
    p.add_argument("--interval", type=float, default=2.0)
    p.add_argument("--count", type=int, default=0, help="0 = run forever")
    args = p.parse_args()

    client = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="sensor-simulator")
    client.connect(args.host, args.port)
    client.loop_start()

    sent = 0
    try:
        while args.count == 0 or sent < args.count:
            for n in range(1, args.sensors + 1):
                payload = {
                    "temperature": round(random.uniform(22, 34), 1),
                    "humidity": round(random.uniform(55, 85), 1),
                }
                topic = f"greenhouse/sensor/sensor-{n:02d}"
                client.publish(topic, json.dumps(payload), qos=1)
                print(topic, payload)
            sent += 1
            time.sleep(args.interval)
    except KeyboardInterrupt:
        pass
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
