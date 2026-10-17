import pytest

VALID = {"sensor_id": "sensor-01", "temperature": 28.5, "humidity": 72.3, "timestamp": "2026-09-21T10:00:00Z"}


def test_ingest_success_and_persisted(client):
    r = client.post("/sensor-data", json=VALID)
    assert r.status_code == 201
    body = r.json()
    assert body["success"] is True
    assert body["data"]["sensor_id"] == "sensor-01"
    assert body["data"]["timestamp"] == "2026-09-21T10:00:00Z"
    assert body["data"]["source"] == "http"

    rows = client.get("/sensor-data").json()["data"]
    assert len(rows) == 1 and rows[0]["temperature"] == 28.5


def test_timestamp_defaults_to_server_time(client):
    payload = {k: v for k, v in VALID.items() if k != "timestamp"}
    r = client.post("/sensor-data", json=payload)
    assert r.status_code == 201
    assert r.json()["data"]["timestamp"].endswith("Z")


def test_timezone_offset_normalised_to_utc(client):
    r = client.post("/sensor-data", json={**VALID, "timestamp": "2026-09-21T17:00:00+07:00"})
    assert r.status_code == 201
    assert r.json()["data"]["timestamp"] == "2026-09-21T10:00:00Z"


def test_integers_are_accepted_as_numbers(client):
    r = client.post("/sensor-data", json={**VALID, "temperature": 30, "humidity": 80})
    assert r.status_code == 201


@pytest.mark.parametrize("missing", ["sensor_id", "temperature", "humidity"])
def test_missing_required_field(client, missing):
    payload = {k: v for k, v in VALID.items() if k != missing}
    r = client.post("/sensor-data", json=payload)
    assert r.status_code == 422
    err = r.json()["error"]
    assert err["code"] == "VALIDATION_ERROR"
    assert err["details"][0]["field"] == missing


@pytest.mark.parametrize(
    "field,value",
    [
        ("temperature", "28.5"),  # numeric string
        ("temperature", True),  # boolean is not a number
        ("temperature", None),
        ("humidity", "high"),
        ("sensor_id", 123),
        ("timestamp", "not-a-date"),
    ],
)
def test_wrong_types_rejected(client, field, value):
    r = client.post("/sensor-data", json={**VALID, field: value})
    assert r.status_code == 422
    assert r.json()["error"]["details"][0]["field"] == field


@pytest.mark.parametrize(
    "field,value",
    [("humidity", 100.1), ("humidity", -1), ("temperature", 150), ("temperature", -80)],
)
def test_out_of_range_rejected(client, field, value):
    r = client.post("/sensor-data", json={**VALID, field: value})
    assert r.status_code == 422


def test_future_timestamp_rejected(client):
    r = client.post("/sensor-data", json={**VALID, "timestamp": "2999-01-01T00:00:00Z"})
    assert r.status_code == 422
    assert "future" in r.json()["error"]["details"][0]["message"]


@pytest.mark.parametrize("sensor_id", ["", "a/b", "a#", "a+b", "has space", "x" * 65])
def test_bad_sensor_id_rejected(client, sensor_id):
    assert client.post("/sensor-data", json={**VALID, "sensor_id": sensor_id}).status_code == 422


def test_malformed_json_is_400(client):
    r = client.post("/sensor-data", content="{bad json", headers={"Content-Type": "application/json"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "MALFORMED_JSON"


def test_empty_body_is_422(client):
    assert client.post("/sensor-data").status_code == 422


def test_unknown_extra_fields_ignored(client):
    assert client.post("/sensor-data", json={**VALID, "battery": 91}).status_code == 201


def test_list_filter_and_limit(client):
    for i in range(3):
        client.post("/sensor-data", json={**VALID, "sensor_id": "s-a", "temperature": 20 + i})
    client.post("/sensor-data", json={**VALID, "sensor_id": "s-b"})
    assert len(client.get("/sensor-data?sensor_id=s-a").json()["data"]) == 3
    assert len(client.get("/sensor-data?limit=2").json()["data"]) == 2
    assert client.get("/sensor-data?limit=0").status_code == 422


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"
    assert "X-Request-ID" in r.headers
