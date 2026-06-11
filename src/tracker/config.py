"""Configuration for BerkeleyTracker via environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MQTT
    mqtt_broker: str = "localhost"
    mqtt_port: int = 1883

    # InfluxDB
    influxdb_url: str = "http://localhost:8086"
    influxdb_token: str = ""
    influxdb_org: str = "berkeley"

    # ADS-B (dump1090)
    adsb_host: str = "localhost"
    adsb_sbs_port: int = 30003
    adsb_json_port: int = 30047

    # AIS (AIS-catcher)
    ais_udp_port: int = 10110

    # SDR serial numbers
    sdr_adsb_serial: str = "ADSB001"
    sdr_ais_serial: str = "AIS001"

    # Enrichment APIs
    opensky_username: str = ""
    opensky_password: str = ""
    flightaware_api_key: str = ""
    marine_traffic_api_key: str = ""

    # Dashboard
    dashboard_url: str = "http://localhost:5050/api/ingest/tracker"

    # Storage
    tracker_db_path: str = "/var/lib/berkeley/tracker.db"
    photo_dir: str = "/data/photos"

    # Logging
    log_level: str = "INFO"

    # API
    api_port: int = 8083
