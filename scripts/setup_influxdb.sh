#!/usr/bin/env bash
# Create InfluxDB buckets for tracker data
set -euo pipefail

INFLUX_URL="${INFLUXDB_URL:-http://localhost:8086}"
INFLUX_TOKEN="${INFLUXDB_TOKEN:?INFLUXDB_TOKEN must be set}"
INFLUX_ORG="${INFLUXDB_ORG:-berkeley}"

echo "Creating InfluxDB buckets for BerkeleyTracker..."

influx bucket create --name tracker-raw    --retention 7d   --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  tracker-raw already exists"
influx bucket create --name tracker-hourly --retention 365d --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  tracker-hourly already exists"
influx bucket create --name tracker-daily  --retention 0    --org "$INFLUX_ORG" --host "$INFLUX_URL" --token "$INFLUX_TOKEN" 2>/dev/null || echo "  tracker-daily already exists"

echo "Done. Buckets: tracker-raw (7d), tracker-hourly (1y), tracker-daily (forever)"
