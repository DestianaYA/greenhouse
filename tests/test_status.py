def test_all_healthy(client):
    r = client.get("/status")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert (body["service"], body["database"], body["mqtt"]) == ("ok", "connected", "connected")
    assert body["uptime_seconds"] >= 0


def test_mqtt_down_is_503(client, mqtt):
    mqtt.is_connected = False
    r = client.get("/status")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "degraded"
    assert body["mqtt"] == "disconnected" and body["database"] == "connected"


def test_database_down_is_503(client, monkeypatch):
    monkeypatch.setattr(client.app.state.db, "check_connection", lambda: False)
    r = client.get("/status")
    assert r.status_code == 503
    assert r.json()["database"] == "disconnected" and r.json()["mqtt"] == "connected"


def test_real_unreachable_database(make_client, settings):
    settings.database_url = "sqlite:////nonexistent-dir/x/y.db"
    c = make_client(settings)  # app must still boot in degraded mode
    r = c.get("/status")
    assert r.status_code == 503 and r.json()["database"] == "disconnected"


def test_sensor_post_with_dead_database_is_503(make_client, settings):
    settings.database_url = "sqlite:////nonexistent-dir/x/y.db"
    c = make_client(settings)
    r = c.post("/sensor-data", json={"sensor_id": "s1", "temperature": 20, "humidity": 50})
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


def test_recovers_without_restart_when_db_comes_back(make_client, settings, tmp_path):
    """App boots while the DB is unreachable; once it is reachable, the first request works."""
    later = tmp_path / "later"
    settings.database_url = f"sqlite:///{later / 'x.db'}"  # directory does not exist yet
    c = make_client(settings)
    payload = {"sensor_id": "s1", "temperature": 20, "humidity": 50}
    assert c.post("/sensor-data", json=payload).status_code == 503

    later.mkdir()  # "database comes back"
    assert c.post("/sensor-data", json=payload).status_code == 201  # tables created lazily
    assert c.get("/status").json()["database"] == "connected"
