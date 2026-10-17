import json

from app.models import SensorReading


def _rows(client):
    with client.app.state.db.session_factory() as db:
        return db.query(SensorReading).all()


def test_app_subscribes_to_sensor_topic(client, mqtt):
    assert "greenhouse/sensor/+" in mqtt.subscriptions


def test_valid_message_is_stored_with_topic_sensor_id(client, mqtt):
    handler = mqtt.subscriptions["greenhouse/sensor/+"]
    handler("greenhouse/sensor/sensor-07", json.dumps({"temperature": 25.1, "humidity": 60}).encode())
    rows = _rows(client)
    assert len(rows) == 1
    assert rows[0].sensor_id == "sensor-07" and rows[0].source == "mqtt"


def test_topic_wins_over_payload_sensor_id(client, mqtt):
    handler = mqtt.subscriptions["greenhouse/sensor/+"]
    handler("greenhouse/sensor/real", json.dumps({"sensor_id": "spoof", "temperature": 1, "humidity": 1}).encode())
    assert _rows(client)[0].sensor_id == "real"


def test_bad_messages_are_dropped_without_raising(client, mqtt):
    handler = mqtt.subscriptions["greenhouse/sensor/+"]
    handler("greenhouse/sensor/s1", b"not json")
    handler("greenhouse/sensor/s1", b"[1,2,3]")
    handler("greenhouse/sensor/s1", b'{"temperature": "hot", "humidity": 50}')
    handler("greenhouse/sensor/s1", b'{"temperature": 20, "humidity": 500}')
    handler("greenhouse/sensor/s1", b"\xff\xfe")
    assert _rows(client) == []
