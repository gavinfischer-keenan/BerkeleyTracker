#!/usr/bin/env bash
# =============================================================================
# Detect connected RTL-SDR devices and show their assignments
# =============================================================================
set -euo pipefail

echo "╔═══════════════════════════════════════════════╗"
echo "║  RTL-SDR Device Detection                     ║"
echo "╚═══════════════════════════════════════════════╝"
echo ""

if ! command -v rtl_test &>/dev/null; then
    echo "❌ rtl_test not found. Install rtl-sdr: apt install rtl-sdr"
    exit 1
fi

# Run rtl_test briefly to enumerate devices
output=$(timeout 2 rtl_test 2>&1 || true)

echo "$output" | grep -E "^\s+[0-9]+:" || echo "  No devices found"

echo ""
echo "Expected assignments:"
echo "  Serial ADSB001 → dump1090-fa (ADS-B 1090 MHz)"
echo "  Serial AIS001  → AIS-catcher (AIS 161.975 MHz)"
echo ""
echo "To set serial numbers:"
echo "  rtl_eeprom -d 0 -s ADSB001"
echo "  rtl_eeprom -d 1 -s AIS001"
