# Berkeley Tracker — ADS-B & AIS via SDR

Aircraft and marine vessel tracking for the Berkeley Home Intelligence Platform using two RTL-SDR dongles.

## What It Does

- **Tracks aircraft** via ADS-B (1090 MHz) using dump1090-fa
- **Tracks vessels** via AIS (161.975 MHz) using AIS-catcher
- **Builds a registry** of every craft ever seen (SQLite)
- **Learns routes** — identifies ferry schedules, patrol patterns, commuter flights
- **Counts sightings** — "How often does the Coast Guard pass?"
- **Attaches photos** — upload photos of specific aircraft/vessels
- **Enriches data** — queries OpenSky, FlightAware, MarineTraffic APIs
- **Publishes to MQTT** — feeds the home intelligence bus

## Architecture

```
  RTL-SDR #1 (1090 MHz) → dump1090-fa → SBS TCP:30003 ─┐
  RTL-SDR #2 (VHF Marine) → AIS-catcher → UDP:10110 ───┤
                                                         ▼
                              BerkeleyTracker (this service)
                              ├── Ingest (SBS + NMEA parsing)
                              ├── Registry (SQLite: aircraft, vessels)
                              ├── Route Learner (pattern clustering)
                              ├── Enrichment (OpenSky, FlightAware, MarineTraffic)
                              ├── Photos (per-craft image storage)
                              ├── MQTT Publisher (home/events/tracker/*)
                              ├── InfluxDB Writer (position telemetry)
                              └── FastAPI (/api/tracker/*)
```

## MQTT Topics

| Topic | QoS | Description |
|-------|-----|-------------|
| `home/events/tracker/aircraft-seen` | 1 | Aircraft sighting (new or returning) |
| `home/events/tracker/vessel-seen` | 1 | Vessel sighting |
| `home/events/tracker/aircraft-new` | 1 | First-ever aircraft sighting |
| `home/events/tracker/vessel-new` | 1 | First-ever vessel sighting |
| `home/events/tracker/route-learned` | 1 | New route pattern identified |
| `home/events/tracker/notable` | 1 | Coast Guard, military, unusual craft |
| `home/status/tracker` | 0 | Agent heartbeat (retained) |

## Quick Start

```bash
# 1. Install SDR decoders
sudo ./scripts/install_dump1090.sh    # ADS-B
sudo ./scripts/install_ais_catcher.sh  # AIS

# 2. Assign SDR serial numbers (one-time, prevents USB enumeration issues)
rtl_eeprom -d 0 -s ADSB001
rtl_eeprom -d 1 -s AIS001

# 3. Install tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

# 4. Configure
cp .env.example .env
nano .env

# 5. Run
python -m tracker
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/tracker/aircraft` | All currently visible aircraft |
| GET | `/api/tracker/aircraft/{icao}` | Aircraft detail + history |
| GET | `/api/tracker/aircraft/{icao}/positions?hours=24` | Position trail |
| POST | `/api/tracker/aircraft/{icao}/photo` | Upload photo |
| GET | `/api/tracker/vessels` | All currently visible vessels |
| GET | `/api/tracker/vessels/{mmsi}` | Vessel detail + history |
| POST | `/api/tracker/vessels/{mmsi}/photo` | Upload photo |
| GET | `/api/tracker/routes` | All learned routes |
| GET | `/api/tracker/stats` | Totals: aircraft/vessels/routes |
| GET | `/api/tracker/stats/frequency` | Most-seen craft (top 50) |

## Enrichment Strategy

| Source | Data | Cost |
|--------|------|------|
| OpenSky Network | Registration, type, operator | Free (rate-limited) |
| FlightAware AeroAPI | Route, airline, origin/dest | Paid (20K free/month) |
| MarineTraffic | Vessel name, type, photo | Paid |
| MMSI static table | Flag country from MID digits | Free (built-in) |

Enrichment is **lazy and cached** — data is fetched only on first sighting, then stored permanently.

## Route Learning

The system automatically identifies repeating patterns:
- Ferry boats following the same path 3+ times → scheduled route
- Coast Guard vessels on regular patrol → patrol route
- Commuter flights following consistent corridors → commuter route

Each route stores waypoints, frequency, associated craft IDs, and sighting count.
