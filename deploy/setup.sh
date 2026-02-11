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
USER="tritium"
CONFIG_TXT="/boot/firmware/config.txt"
CMDLINE_TXT="/boot/firmware/cmdline.txt"

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
echo "[1/6] Setting static IP $STATIC_IP..."

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
echo "[2/6] Ensuring SSH is enabled..."
systemctl enable ssh
systemctl start ssh
echo "  SSH enabled"

# --- 3. Composite video output ---
echo "[3/6] Enabling composite video output..."

# config.txt: add ,composite to the vc4-kms-v3d overlay
if grep -q "dtoverlay=vc4-kms-v3d" "$CONFIG_TXT"; then
    if grep -q "composite" "$CONFIG_TXT"; then
        echo "  Composite already enabled in config.txt"
    else
        sed -i 's/dtoverlay=vc4-kms-v3d.*/&,composite/' "$CONFIG_TXT"
        echo "  Added composite to dtoverlay in config.txt"
    fi
else
    echo "dtoverlay=vc4-kms-v3d,composite" >> "$CONFIG_TXT"
    echo "  Added dtoverlay with composite to config.txt"
fi

# cmdline.txt: add video mode for composite NTSC
if grep -q "video=Composite" "$CMDLINE_TXT"; then
    echo "  Composite video mode already in cmdline.txt"
else
    # Append to existing single line (cmdline.txt must be one line)
    sed -i 's/$/ video=Composite-1:720x480i,tv_mode=NTSC/' "$CMDLINE_TXT"
    echo "  Added NTSC composite video mode to cmdline.txt"
fi

echo "  NOTE: Composite output disables HDMI — use SSH to manage"

# --- 4. Dependencies ---
echo "[4/6] Installing Python dependencies..."
pip3 install --break-system-packages -q -r "$REPO_DIR/requirements.txt" 2>/dev/null || \
    pip3 install -r "$REPO_DIR/requirements.txt" 2>/dev/null || \
    echo "  WARNING: pip install failed — run manually: pip3 install -r requirements.txt"
echo "  Dependencies checked"

# --- 5. Autostart (GUI) + systemd (fallback) ---
echo "[5/6] Installing autostart + service..."
# Autostart desktop entry — runs in graphical session, reliable fullscreen
AUTOSTART_DIR="/home/$USER/.config/autostart"
mkdir -p "$AUTOSTART_DIR"
cp "$REPO_DIR/deploy/striker-autostart.desktop" "$AUTOSTART_DIR/striker.desktop"
chown -R "$USER:$USER" "$AUTOSTART_DIR"
echo "  Autostart entry installed"
# Systemd as fallback
cp "$REPO_DIR/deploy/striker.service" /etc/systemd/system/striker.service
systemctl daemon-reload
systemctl disable striker.service 2>/dev/null  # disable systemd, autostart handles it
echo "  Systemd service installed (disabled, autostart preferred)"

# --- 6. Permissions ---
echo "[6/6] Setting permissions..."
usermod -aG dialout "$USER" 2>/dev/null || true  # serial port access
usermod -aG video "$USER" 2>/dev/null || true     # camera access
echo "  User $USER added to dialout + video groups"

echo ""
echo "=== Done ==="
echo "  Static IP:  $STATIC_IP (reconnect or reboot to apply)"
echo "  SSH:        enabled"
echo "  Composite:  enabled (HDMI disabled)"
echo "  Service:    striker.service (starts on boot, auto-restarts)"
echo ""
echo "  Commands:"
echo "    sudo systemctl start striker    # start now"
echo "    sudo systemctl stop striker     # stop"
echo "    sudo systemctl status striker   # check status"
echo "    tail -f ~/striker.log           # view logs"
echo ""
echo "  Reboot to apply all changes: sudo reboot"
