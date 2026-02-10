#!/bin/bash
# STRIKER EDGE AI — Pi setup script
# Usage: sudo ./deploy/setup.sh <static-ip>
# Example: sudo ./deploy/setup.sh 192.168.1.68

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Run with sudo: sudo ./deploy/setup.sh <ip>"
    exit 1
fi

STATIC_IP="${1}"
GATEWAY="${2:-192.168.1.1}"
DNS="${3:-8.8.8.8}"
REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
USER="mackie"

if [ -z "$STATIC_IP" ]; then
    echo "Usage: sudo ./deploy/setup.sh <static-ip> [gateway] [dns]"
    echo "  Example: sudo ./deploy/setup.sh 192.168.1.68"
    exit 1
fi

echo "=== STRIKER Pi Setup ==="
echo "  Repo:    $REPO_DIR"
echo "  IP:      $STATIC_IP"
echo "  Gateway: $GATEWAY"
echo "  DNS:     $DNS"
echo ""

# --- 1. Static IP ---
echo "[1/5] Setting static IP $STATIC_IP..."

# Find active WiFi connection name
WIFI_CON=$(nmcli -t -f NAME,TYPE con show --active | grep wifi | head -1 | cut -d: -f1)
if [ -n "$WIFI_CON" ]; then
    echo "  WiFi connection: $WIFI_CON"
    nmcli con mod "$WIFI_CON" ipv4.addresses "$STATIC_IP/24"
    nmcli con mod "$WIFI_CON" ipv4.gateway "$GATEWAY"
    nmcli con mod "$WIFI_CON" ipv4.dns "$DNS"
    nmcli con mod "$WIFI_CON" ipv4.method manual
    echo "  WiFi static IP configured (takes effect on reconnect)"
else
    # Try ethernet
    ETH_CON=$(nmcli -t -f NAME,TYPE con show --active | grep ethernet | head -1 | cut -d: -f1)
    if [ -n "$ETH_CON" ]; then
        echo "  Ethernet connection: $ETH_CON"
        nmcli con mod "$ETH_CON" ipv4.addresses "$STATIC_IP/24"
        nmcli con mod "$ETH_CON" ipv4.gateway "$GATEWAY"
        nmcli con mod "$ETH_CON" ipv4.dns "$DNS"
        nmcli con mod "$ETH_CON" ipv4.method manual
        echo "  Ethernet static IP configured (takes effect on reconnect)"
    else
        echo "  WARNING: No active WiFi or Ethernet connection found"
        echo "  Set static IP manually with: sudo nmcli con mod <name> ipv4.addresses $STATIC_IP/24 ipv4.method manual"
    fi
fi

# --- 2. SSH ---
echo "[2/5] Ensuring SSH is enabled..."
systemctl enable ssh
systemctl start ssh
echo "  SSH enabled"

# --- 3. Dependencies ---
echo "[3/5] Installing Python dependencies..."
pip3 install --break-system-packages -q pymavlink PyYAML 2>/dev/null || \
    pip3 install pymavlink PyYAML 2>/dev/null || \
    echo "  WARNING: pip install failed — pymavlink/PyYAML may need manual install"
echo "  Dependencies checked"

# --- 4. Systemd service ---
echo "[4/5] Installing striker service..."
cp "$REPO_DIR/deploy/striker.service" /etc/systemd/system/striker.service
systemctl daemon-reload
systemctl enable striker.service
echo "  Service installed and enabled"

# --- 5. Permissions ---
echo "[5/5] Setting permissions..."
usermod -aG dialout "$USER" 2>/dev/null || true  # serial port access
usermod -aG video "$USER" 2>/dev/null || true     # camera access
echo "  User $USER added to dialout + video groups"

echo ""
echo "=== Done ==="
echo "  Static IP: $STATIC_IP (reconnect or reboot to apply)"
echo "  SSH:       enabled"
echo "  Service:   striker.service (starts on boot, auto-restarts)"
echo ""
echo "  Commands:"
echo "    sudo systemctl start striker    # start now"
echo "    sudo systemctl stop striker     # stop"
echo "    sudo systemctl status striker   # check status"
echo "    tail -f ~/striker.log           # view logs"
echo ""
echo "  Reboot to apply all changes: sudo reboot"
