#!/usr/bin/env bash
# Quick manual walk-through of every endpoint. Usage: ./scripts/demo.sh [base_url]
BASE=${1:-http://localhost:8000}
H='Content-Type: application/json'
p() { echo; echo "\$ $*"; }

p "GET /status";                          curl -s -w '\n[HTTP %{http_code}]\n' $BASE/status
p "POST /sensor-data (valid)";            curl -s -w '\n[HTTP %{http_code}]\n' -X POST $BASE/sensor-data -H "$H" \
  -d '{"sensor_id":"sensor-01","temperature":28.5,"humidity":72.3,"timestamp":"2026-09-21T10:00:00Z"}'
p "POST /sensor-data (invalid)";          curl -s -w '\n[HTTP %{http_code}]\n' -X POST $BASE/sensor-data -H "$H" \
  -d '{"sensor_id":"sensor-01","temperature":"hot","humidity":150}'
p "GET /sensor-data";                     curl -s -w '\n[HTTP %{http_code}]\n' "$BASE/sensor-data?limit=3"
p "POST /device-control ON";              curl -s -w '\n[HTTP %{http_code}]\n' -X POST $BASE/device-control -H "$H" \
  ${API_KEY:+-H "X-API-Key: $API_KEY"} -d '{"device_id":"fan-01","command":"ON"}'
p "POST /device-control (bad command)";   curl -s -w '\n[HTTP %{http_code}]\n' -X POST $BASE/device-control -H "$H" \
  ${API_KEY:+-H "X-API-Key: $API_KEY"} -d '{"device_id":"fan-01","command":"TOGGLE"}'
p "POST /device-control (topic injection)"; curl -s -w '\n[HTTP %{http_code}]\n' -X POST $BASE/device-control -H "$H" \
  ${API_KEY:+-H "X-API-Key: $API_KEY"} -d '{"device_id":"#","command":"ON"}'
