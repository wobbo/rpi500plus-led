#!/bin/bash

# 2026-04-18
# Ernst Lanser
# https://forums.raspberrypi.com/
# https://github.com/wobbo/rpi500plus-led/

# RPi 500+ LED Controller remover
#
# Removes the GTK4 RGB keyboard LED controller for
# the Raspberry Pi 500+ keyboard.
#
# This script removes:
#   • /usr/local/bin/rpi500plus-led
#   • desktop launcher
#   • autostart entry
#   • user config (~/.config/rpi500plus-led.json)
#
# Safe to run multiple times.
# Safe on systems without Pi 500+ hardware.

set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

trap 'printf "\n    Installation failed\n\n"' ERR

clear
printf "\n"
printf "  \033[1mWelcome to the RPi 500+ LED Installer\033[0m.\n\n"

###########################################
# Require sudo
###########################################
if [ "$EUID" -ne 0 ]; then
  printf "\n  Run with sudo:\n"
  printf "  sudo ./install-rpi500plus-led.sh\n"
  exit 1
fi


###########################################
# Detect distro
###########################################
if [ -f /etc/os-release ]; then
    . /etc/os-release
fi

IS_RPI_OS=false
IS_GENERIC_DEBIAN=false

if [[ "${ID:-}" == "raspbian" || \
      "${ID:-}" == "raspberrypi" || \
      "${ID_LIKE:-}" == *"raspbian"* || \
      "${ID_LIKE:-}" == *"raspberrypi"* ]]; then

    IS_RPI_OS=true

elif command -v apt >/dev/null 2>&1; then
    IS_GENERIC_DEBIAN=true
fi


###########################################
# Detect Pi 500+ keyboard
###########################################
PI500PLUS_PRESENT=false

if command -v lsusb >/dev/null 2>&1 && \
   lsusb | grep -q "2e8a:0011"; then
    PI500PLUS_PRESENT=true
fi


###########################################
# Install dependencies
###########################################
printf "\n    Installing dependencies...\n"

APT_REQUIRED=(
python3
python3-gi
python3-gi-cairo
gir1.2-gtk-4.0
gir1.2-adw-1
)

if [ "$IS_GENERIC_DEBIAN" = true ]; then
    printf "    Generic Debian/Ubuntu detected\n"
    APT_REQUIRED+=(libhidapi-hidraw0)
elif [ "$IS_RPI_OS" = true ]; then
    printf "    Raspberry Pi OS detected\n"
fi

apt update -qq
apt install -y -qq "${APT_REQUIRED[@]}"


###########################################
# Install udev rule (generic Debian only)
###########################################
if [ "$IS_GENERIC_DEBIAN" = true ] && \
   [ "$PI500PLUS_PRESENT" = true ]; then

    RULE_FILE="/etc/udev/rules.d/99-rpi500kbd.rules"

    if [[ ! -f "$RULE_FILE" ]]; then

        printf "\n    Installing Pi 500+ keyboard access rule\n\n"

        echo 'KERNEL=="hidraw*", ATTRS{idVendor}=="2e8a", ATTRS{idProduct}=="0011", MODE="0666"' \
        > "$RULE_FILE"

        udevadm control --reload-rules
        udevadm trigger
    fi
fi


###########################################
# Install keyboard backend
###########################################
printf "\n    Checking rpi-keyboard-config backend...\n\n"

if command -v rpi-keyboard-config >/dev/null 2>&1; then

    printf "    Backend already installed\n\n"

elif [ "$PI500PLUS_PRESENT" = true ]; then

    if apt-cache show rpi-keyboard-config >/dev/null 2>&1; then

        apt install -y rpi-keyboard-config

    else

        TMP_DEB="/tmp/rpi-keyboard-config.deb"

        printf "    Downloading backend package...\n"

        wget -q \
        https://archive.raspberrypi.org/debian/pool/main/r/rpi-keyboard-config/rpi-keyboard-config_1.0_all.deb \
        -O "$TMP_DEB.tmp"

        mv "$TMP_DEB.tmp" "$TMP_DEB"

        apt install -y "$TMP_DEB"
    fi

else
    printf "    Pi 500+ keyboard not detected — backend skipped\n\n"
fi


###########################################
# Install application
###########################################
printf "\n    Installing RPi 500+ LED application...\n\n"

URL_PY="https://wobbo.org/install/2026-04-17/rpi500plus-led.py"

TARGET_BIN="/usr/local/bin/rpi500plus-led"
TARGET_DESKTOP="/usr/share/applications/rpi500plus-led.desktop"

wget -q -O "$TARGET_BIN.tmp" "$URL_PY"

chmod 755 "$TARGET_BIN.tmp"
mv "$TARGET_BIN.tmp" "$TARGET_BIN"


###########################################
# Install desktop entry
###########################################
cat <<EOF > "$TARGET_DESKTOP"
[Desktop Entry]
Version=1.0
Type=Application
Name=RPi 500+ LED
Exec=$TARGET_BIN
Icon=preferences-desktop-keyboard
Terminal=false
Categories=Settings;HardwareSettings;
Keywords=led;keyboard;raspberry;color;
EOF

chmod 644 "$TARGET_DESKTOP"

update-desktop-database >/dev/null 2>&1 || true


###########################################
# Cleanup legacy configs
###########################################
printf "    Cleaning up legacy autostart configs...\n"

for home in /home/*; do
    if [ -d "$home" ]; then
        rm -f "$home/.config/autostart/rpi500plus-led.desktop"
    fi
done


###########################################
# Remove installer itself
###########################################
SCRIPT_PATH="$(realpath "$0" 2>/dev/null || echo '')"

if [ -n "$SCRIPT_PATH" ] && [ -f "$SCRIPT_PATH" ]; then
    rm -f "$SCRIPT_PATH"
fi


###########################################
# Done
###########################################
printf "\n\n"
printf "  ╔═════════════ \033[1mRPi 500+ LED – Complete\033[0m ════════════════╗\n"
printf "  ║   Installation complete.                             ║\n"
printf "  ║   Done.                                              ║\n"
printf "  ╙──────────────────────────────────────────────────────╜\n\n"
