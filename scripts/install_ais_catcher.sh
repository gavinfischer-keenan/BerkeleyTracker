#!/usr/bin/env bash
# =============================================================================
# Install AIS-catcher (AIS decoder for RTL-SDR)
# =============================================================================
# Builds AIS-catcher from source and creates a systemd service.
# Outputs decoded AIS NMEA sentences via UDP to port 10110.
#
# Usage: sudo ./scripts/install_ais_catcher.sh
# =============================================================================
set -euo pipefail

AIS_DIR="/opt/AIS-catcher"
SDR_SERIAL="${SDR_AIS_SERIAL:-AIS001}"
UDP_PORT="${AIS_UDP_PORT:-10110}"

echo "▶ Installing AIS-catcher..."

# Dependencies
apt-get update -qq
apt-get install -y -qq git cmake build-essential pkg-config \
    librtlsdr-dev libusb-1.0-0-dev

# Clone and build
if [ ! -d "$AIS_DIR" ]; then
    git clone https://github.com/jvde-github/AIS-catcher.git "$AIS_DIR"
fi

cd "$AIS_DIR"
git pull origin main 2>/dev/null || true
mkdir -p build && cd build
cmake .. -DCMAKE_BUILD_TYPE=Release
make -j"$(nproc)"
make install

echo "✅ AIS-catcher built and installed"

# Create systemd service
cat > /etc/systemd/system/ais-catcher.service <<EOF
[Unit]
Description=AIS-catcher (RTL-SDR AIS Decoder)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/AIS-catcher -d ${SDR_SERIAL} -u 127.0.0.1 ${UDP_PORT}
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable ais-catcher
systemctl restart ais-catcher

echo "✅ AIS-catcher systemd service running"
echo "   SDR serial: ${SDR_SERIAL}"
echo "   UDP output: localhost:${UDP_PORT}"
