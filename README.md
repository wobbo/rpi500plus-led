# RPi 500+ LED Controller

GTK4 application to control the RGB keyboard lighting on the Raspberry Pi 500+ keyboard.

Supports:

• Raspberry Pi OS (Trixie or newer)
• Ubuntu 24.04+ on Raspberry Pi

The application allows:

• changing keyboard LED color
• changing brightness
• turning LEDs on/off
• restoring LED settings automatically at login

---

## Install (recommended)

Run the official installer:

wget -O install-rpi500plus-led.sh https://wobbo.org/install/2026-04-18/install-rpi500plus-led.sh
chmod +x install-rpi500plus-led.sh
sudo ./install-rpi500plus-led.sh

The installer automatically:

• installs dependencies
• installs the keyboard backend when needed
• applies required Ubuntu HID permissions
• installs desktop launcher integration

---

## Remove

wget -O remove-rpi500plus-led.sh https://wobbo.org/install/2026-04-18/remove-rpi500plus-led.sh
chmod +x remove-rpi500plus-led.sh
sudo ./remove-rpi500plus-led.sh

---

## Manual backend requirement

Raspberry Pi OS:

sudo apt install rpi-keyboard-config

Ubuntu:

Handled automatically by the installer.

---

## Configuration

Stored in:

~/.config/rpi500plus-led.json

Restore last LED state:

rpi500plus-led --restore

---

Safe to run multiple times  
Safe on non-Pi-500 hardware  
No changes are made if unsupported hardware is detected
