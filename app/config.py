"""Application settings, loaded from environment variables / .env file."""
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- General ---
    app_name: str = "Greenhouse Backend"
    app_version: str = "1.0.0"
    log_level: str = "INFO"

    # --- Database ---
    # MySQL example: mysql+pymysql://user:pass@localhost:3306/greenhouse
    database_url: str = "sqlite:///./greenhouse.db"
    db_startup_retries: int = Field(5, ge=1)
    db_startup_retry_delay: float = Field(2.0, ge=0)

    # --- MQTT ---
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str | None = None
    mqtt_password: str | None = None
    mqtt_client_id_prefix: str = "greenhouse-backend"
    mqtt_keepalive: int = 30
    mqtt_control_topic_prefix: str = "greenhouse/control"
    mqtt_control_qos: int = Field(1, ge=0, le=2)
    mqtt_control_retain: bool = True
    mqtt_publish_timeout: float = Field(3.0, gt=0)
    mqtt_subscribe_sensors: bool = True
    mqtt_sensor_topic_prefix: str = "greenhouse/sensor"
    mqtt_status_topic: str = "greenhouse/backend/status"

    # --- Security ---
    # If set, POST /device-control requires header "X-API-Key: <value>".
    api_key: str | None = None


@lru_cache
def get_settings() -> Settings:
    return Settings()
