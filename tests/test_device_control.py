import json

import pytest

from app.database import Database


def test_command_published_to_structured_topic(client, mqtt):
    r = client.post("/device-control", json={"device_id": "fan-01", "command": "ON"})
    assert r.status_code == 202
    data = r.json()["data"]
    assert data["topic"] == "greenhouse/control/fan-01"
    assert data["status"] == "PUBLISHED"

    assert len(mqtt.published) == 1
    msg = mqtt.published[0]
    assert msg["topic"] == "greenhouse/control/fan-01"
    assert msg["qos"] == 1 and msg["retain"] is True
    payload = json.loads(msg["payload"])
    assert payload["command"] == "ON" and payload["device_id"] == "fan-01"
    assert payload["command_id"] == data["command_id"]


@pytest.mark.parametrize("raw,expected", [("on", "ON"), (" Off ", "OFF"), ("OFF", "OFF")])
def test_command_is_normalised(client, mqtt, raw, expected):
    assert client.post("/device-control", json={"device_id": "vent-1", "command": raw}).status_code == 202
    assert json.loads(mqtt.published[-1]["payload"])["command"] == expected


@pytest.mark.parametrize("command", ["TOGGLE", "", "1", 1, None, True])
def test_invalid_command_rejected(client, mqtt, command):
    r = client.post("/device-control", json={"device_id": "fan-01", "command": command})
    assert r.status_code == 422
    assert not mqtt.published


@pytest.mark.parametrize("device_id", ["", "fan/01", "#", "+", "a/#", "greenhouse/control/x", "sp ace", 5])
def test_topic_injection_rejected(client, mqtt, device_id):
    r = client.post("/device-control", json={"device_id": device_id, "command": "ON"})
    assert r.status_code == 422
    assert not mqtt.published


def test_missing_fields(client, mqtt):
    assert client.post("/device-control", json={"command": "ON"}).status_code == 422
    assert client.post("/device-control", json={"device_id": "fan-01"}).status_code == 422
    assert not mqtt.published


def test_broker_down_returns_503_and_is_audited(client, mqtt):
    mqtt.is_connected = False
    r = client.post("/device-control", json={"device_id": "fan-01", "command": "ON"})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "MQTT_UNAVAILABLE"
    assert not mqtt.published

    from app.models import DeviceCommandRecord

    with client.app.state.db.session_factory() as db:
        rows = db.query(DeviceCommandRecord).all()
    assert len(rows) == 1 and rows[0].status == "FAILED"


def test_publish_timeout_returns_504(client, mqtt):
    mqtt.timeout = True
    r = client.post("/device-control", json={"device_id": "fan-01", "command": "ON"})
    assert r.status_code == 504
    assert r.json()["error"]["code"] == "MQTT_PUBLISH_TIMEOUT"


def test_success_is_audited(client):
    client.post("/device-control", json={"device_id": "pump-2", "command": "OFF"})
    from app.models import DeviceCommandRecord

    with client.app.state.db.session_factory() as db:
        rec = db.query(DeviceCommandRecord).one()
    assert (rec.device_id, rec.command, rec.status) == ("pump-2", "OFF", "PUBLISHED")


def test_db_down_does_not_block_publish(client, mqtt, monkeypatch):
    """The audit log is best-effort: MQTT publish still succeeds if the DB is unavailable."""
    from sqlalchemy.exc import OperationalError

    def boom(self, record):
        raise OperationalError("INSERT", {}, Exception("db down"))

    monkeypatch.setattr("app.repositories.device_command_repository.DeviceCommandRepository.add", boom)
    r = client.post("/device-control", json={"device_id": "fan-01", "command": "ON"})
    assert r.status_code == 202
    assert len(mqtt.published) == 1


class TestApiKey:
    @pytest.fixture
    def secured(self, make_client, settings):
        settings.api_key = "s3cret"
        return make_client(settings)

    def test_missing_key(self, secured, mqtt):
        r = secured.post("/device-control", json={"device_id": "fan-01", "command": "ON"})
        assert r.status_code == 401 and not mqtt.published

    def test_wrong_key(self, secured):
        r = secured.post(
            "/device-control", json={"device_id": "fan-01", "command": "ON"}, headers={"X-API-Key": "nope"}
        )
        assert r.status_code == 401

    def test_valid_key(self, secured, mqtt):
        r = secured.post(
            "/device-control", json={"device_id": "fan-01", "command": "ON"}, headers={"X-API-Key": "s3cret"}
        )
        assert r.status_code == 202 and len(mqtt.published) == 1

    def test_other_endpoints_stay_open(self, secured):
        assert secured.get("/status").status_code == 200
