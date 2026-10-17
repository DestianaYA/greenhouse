import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.core.exceptions import MqttPublishTimeoutError, MqttUnavailableError
from app.main import create_app


class FakeMqtt:
    """In-memory stand-in for MqttService (no broker needed for unit/API tests)."""

    def __init__(self):
        self.is_connected = True
        self.timeout = False
        self.published: list[dict] = []
        self.subscriptions: dict = {}

    def start(self): ...
    def stop(self): ...

    def subscribe(self, topic_filter, handler, qos=1):
        self.subscriptions[topic_filter] = handler

    def publish(self, topic, payload, qos, retain, timeout):
        if not self.is_connected:
            raise MqttUnavailableError()
        if self.timeout:
            raise MqttPublishTimeoutError()
        self.published.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})


@pytest.fixture
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        db_startup_retries=1,
        db_startup_retry_delay=0,
        log_level="WARNING",
        api_key=None,
    )


@pytest.fixture
def mqtt():
    return FakeMqtt()


@pytest.fixture
def make_client(mqtt):
    clients = []

    def _make(settings):
        client = TestClient(create_app(settings, mqtt_service=mqtt), raise_server_exceptions=False)
        client.__enter__()
        clients.append(client)
        return client

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(make_client, settings):
    return make_client(settings)
