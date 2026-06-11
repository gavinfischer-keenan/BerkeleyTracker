#!/usr/bin/env bash
# =============================================================================
# Install dump1090-fa (FlightAware ADS-B decoder)
# =============================================================================
# Installs dump1090-fa from the FlightAware apt repository and configures
# it to use the RTL-SDR dongle with serial ADSB001.
#
# Usage: sudo ./scripts/install_dump1090.sh
# =============================================================================
set -euo pipefail

echo "▶ Installing dump1090-fa (ADS-B decoder)..."

# Add FlightAware repository
if [ ! -f /etc/apt/sources.list.d/flightaware.list ]; then
    wget -qO - https://flightaware.com/adsb/piaware/files/packages.gpg.key | \
        gpg --dearmor > /usr/share/keyrings/flightaware-archive-keyring.gpg
    echo "deb [signed-by=/usr/share/keyrings/flightaware-archive-keyring.gpg] \
        https://flightaware.com/adsb/piaware/files/packages $(lsb_release -cs) flightaware" \
        > /etc/apt/sources.list.d/flightaware.list
    apt-get update -qq
fi

apt-get install -y -qq dump1090-fa

# Configure for specific SDR serial
CONF="/etc/default/dump1090-fa"
if [ -f "$CONF" ]; then
    # Set device serial so dump1090 always grabs the right dongle
    sed -i 's/^RECEIVER_SERIAL=.*/RECEIVER_SERIAL="ADSB001"/' "$CONF" 2>/dev/null || \
        echo 'RECEIVER_SERIAL="ADSB001"' >> "$CONF"

    # Enable SBS output on port 30003 (BaseStation format)
    sed -i 's/^RECEIVER_OPTIONS=.*/RECEIVER_OPTIONS="--device-type rtlsdr --device ADSB001 --net"/' "$CONF" 2>/dev/null || true
fi

# Enable and start
systemctl enable dump1090-fa
systemctl restart dump1090-fa

echo "✅ dump1090-fa installed and running"
echo "   SBS output: localhost:30003"
echo "   JSON output: localhost:30047"
echo "   Web UI: http://localhost:8080"
