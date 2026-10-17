"""Domain-level errors. Each maps to one HTTP status and one machine-readable code."""


class AppError(Exception):
    status_code = 500
    code = "INTERNAL_ERROR"
    message = "Internal server error"

    def __init__(self, message: str | None = None, details: list[dict] | None = None):
        self.message = message or self.message
        self.details = details or []
        super().__init__(self.message)


class UnauthorizedError(AppError):
    status_code = 401
    code = "UNAUTHORIZED"
    message = "Missing or invalid API key"


class MqttUnavailableError(AppError):
    status_code = 503
    code = "MQTT_UNAVAILABLE"
    message = "MQTT broker is not connected"


class MqttPublishError(AppError):
    status_code = 503
    code = "MQTT_PUBLISH_FAILED"
    message = "Failed to publish message to MQTT broker"


class MqttPublishTimeoutError(AppError):
    status_code = 504
    code = "MQTT_PUBLISH_TIMEOUT"
    message = "Timed out waiting for MQTT broker acknowledgement"
