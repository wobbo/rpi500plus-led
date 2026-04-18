#!/usr/bin/env python3

# 2026-04-18
# Ernst Lanser <ernst.lanser@wobbo.org>
# https://forums.raspberrypi.com/
# https://github.com/wobbo/rpi500plus-led/

# RPi 500+ LED Controller
#
# GTK4 application to control the RGB keyboard lighting
# on the Raspberry Pi 500+ keyboard.
#
# Supported systems:
#   • Raspberry Pi OS (Trixie or newer)
#   • Ubuntu 24.04+ on Raspberry Pi
#
# Other Linux distributions may work but are not officially tested.
#
# Recommended installation method:
# wget -O install-rpi500plus-led.sh https://wobbo.org/install/2026-04-18/install-rpi500plus-led.sh
# chmod +x install-rpi500plus-led.sh
# sudo ./install-rpi500plus-led.sh
#
# The installer automatically:
#   • installs required dependencies
#   • installs the keyboard backend when Pi 500+ hardware is detected
#   • applies required Ubuntu HID access rules when needed
#
# Manual dependency installation (GUI only):
# sudo apt install python3 python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1 libhidapi-hidraw0
#
# Backend requirement:
# Raspberry Pi OS:
#   sudo apt install rpi-keyboard-config
#
# Ubuntu:
#   The backend is installed automatically by the installer script.
#   Manual installation instructions are available on:
#   https://github.com/wobbo/rpi500plus-led
#
# Installed files:
# System:
#   /usr/local/bin/rpi500plus-led
#   /usr/share/applications/rpi500plus-led.desktop
#
# User configuration:
#   ~/.config/rpi500plus-led.json
#
# Autostart entry:
#   ~/.config/autostart/rpi500plus-led.desktop
#
# Startup mode:
# Automatically restores saved keyboard LED settings at login:
#   rpi500plus-led --restore
#
# Remove:
# wget -O remove-rpi500plus-led.sh https://wobbo.org/install/2026-04-18/remove-rpi500plus-led.sh
# chmod +x remove-rpi500plus-led.sh
# sudo ./remove-rpi500plus-led.sh
#
# Safe to run multiple times.
# Safe to run on other Raspberry Pi models.
# No changes are made if unsupported hardware is detected.

from __future__ import annotations
import colorsys
import json
import math
import os
import re
import subprocess
import sys
import threading
import queue
from dataclasses import dataclass
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gio, GLib, Gtk  # type: ignore

# Configuration and Global Constants
APP_ID = "com.rpi500.led.app.v432"
WINDOW_TITLE = "Raspberry 500+ LED v4.32"
CONFIG_FILE = Path(GLib.get_home_dir()) / ".config" / "rpi500plus-led.json"
INSTALL_PATH = "/usr/local/bin/rpi500plus-led"

# --- CLASSES ---

@dataclass
# Description:
# Stores the current UI state so values stay together for once.
class AppState:
    hue: float = 0.0     
    x: float = 0.0
    y: float = 0.0
    effect: str = "1. Direct"

# Description:
# Talks to rpi-keyboard-config in the background so the UI does not act dead.
class Backend:
    # Description:
    # Sets up backend state and starts the worker thread.
    # "self" Backend instance managing queued LED commands.
    def __init__(self):
        self._queue = queue.Queue()
        self.last_effect = None
        self.last_hue = None
        self.last_sat = None
        self.last_brightness = None
        self.last_rgb = None
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    # Description:
    # Processes queued backend commands one by one. Revolutionary concept.
    # "self" Backend instance running the worker loop.
    def _worker(self):
        while True:
            task, args = self._queue.get()
            if task == "direct":
                self._apply_direct(*args)
            elif task == "effect":
                self._apply_effect(*args)
            elif task == "off":
                if self.last_effect != "Off":
                    self.run("effect", "Off")
                    self.last_effect = "Off"
            self._queue.task_done()

    # Description:
    # Drops stale queued commands so old input does not linger around.
    # "self" Backend instance clearing pending tasks.
    def _clear_queue(self):
        while True:
            try:
                self._queue.get_nowait()
                self._queue.task_done()
            except queue.Empty:
                break

    # Description:
    # Waits until all queued backend work is finished.
    # "self" Backend instance waiting for the queue to empty.
    def flush(self):
        self._queue.join()

    # Description:
    # Runs the backend tool and returns the result without pretending it is magic.
    # "self" Backend instance executing the command.
    # "args" Arguments passed to rpi-keyboard-config.
    def run(self, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                ["rpi-keyboard-config", *args],
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="Backend tool not found")

    # Description:
    # Reads available LED effects from the backend tool.
    # "self" Backend instance requesting the effect list.
    def list_effects(self) -> list[str]:
        result = self.run("list-effects")
        effects: list[str] = []
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                m = re.search(r"ID\s+(\d+):\s+(.+)", line)
                if not m: continue
                effect_id = m.group(1)
                name = m.group(2).strip()
                if name == "(no name)": continue
                effects.append(f"{effect_id}. {name}")
        if not any(e.startswith("0.") for e in effects):
            effects.insert(0, "0. Off")
        return effects or ["0. Off"]

    # Description:
    # Queues a direct RGB update.
    # "self" Backend instance scheduling the update.
    # "r" Red channel value.
    # "g" Green channel value.
    # "b" Blue channel value.
    def apply_direct(self, r: int, g: int, b: int) -> None:
        self._clear_queue()
        self._queue.put(("direct", (r, g, b)))

    # Description:
    # Applies direct RGB values when something actually changed.
    # "self" Backend instance applying direct color.
    # "r" Red channel value.
    # "g" Green channel value.
    # "b" Blue channel value.
    def _apply_direct(self, r: int, g: int, b: int) -> None:
        if self.last_effect != "Direct":
            self.run("effect", "Direct")
            self.last_effect = "Direct"
            self.last_rgb = None 
        if self.last_rgb != (r, g, b):
            self.run("leds", "set", "--colour", f"rgb({r},{g},{b})")
            self.last_rgb = (r, g, b)

    # Description:
    # Queues an animated LED effect update.
    # "self" Backend instance scheduling the effect.
    # "effect" Effect ID string.
    # "hue" Hue value.
    # "sat" Saturation value.
    # "brightness" Brightness value.
    def apply_effect(self, effect: str, hue: int, sat: int, brightness: int) -> None:
        self._clear_queue()
        self._queue.put(("effect", (effect, hue, sat, brightness)))

    # Description:
    # Applies effect, hue, saturation and brightness if needed.
    # "self" Backend instance applying effect settings.
    # "effect" Effect ID string.
    # "hue" Hue value.
    # "sat" Saturation value.
    # "brightness" Brightness value.
    def _apply_effect(self, effect: str, hue: int, sat: int, brightness: int) -> None:
        h = clamp(hue)
        s = clamp(sat)
        b = clamp(brightness)
        
        # State bug gefixt: de conditie checken voordat variabelen worden overschreven
        effect_changed = (effect != self.last_effect or self.last_hue != h or self.last_sat != s)
        
        if effect_changed:
            self.run("effect", effect, "--hue", str(h), "--sat", str(s))
            self.last_effect = effect
            self.last_hue = h
            self.last_sat = s
            
        if effect_changed or self.last_brightness != b:
            self.run("brightness", str(b))
            self.last_brightness = b

    # Description:
    # Queues a request to switch the LEDs off.
    # "self" Backend instance scheduling LED shutdown.
    def apply_off(self) -> None:
        self._clear_queue()
        self._queue.put(("off", ()))

# Description:
# Vertical hue picker. Simple job, lots of colors, no drama.
class HueBar(Gtk.DrawingArea):
    # Description:
    # Builds the hue picker widget and wires up input handlers.
    # "self" HueBar widget instance.
    # "on_changed" Callback fired after the hue changes.
    def __init__(self, on_changed):
        super().__init__()
        self.set_focusable(True) 
        self.set_content_width(20)
        self.set_content_height(300)
        self.hue = 0.0
        self.on_changed = on_changed
        self.set_draw_func(self.do_draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_press)
        self.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        self.add_controller(drag)

    # Description:
    # Draws the hue gradient and the selection marker.
    # "self" HueBar widget instance.
    # "area" Drawing area argument from GTK.
    # "cr" Cairo drawing context.
    # "width" Current drawing width.
    # "height" Current drawing height.
    def do_draw(self, area, cr, width, height):
        for y in range(height):
            h = y / max(1, height - 1)
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            cr.set_source_rgb(r, g, b)
            cr.rectangle(0, y, width, 1)
            cr.fill()
        y = int(self.hue * (height - 1))
        cr.set_source_rgb(1, 1, 1)
        cr.arc(width / 2, y, 7, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.stroke()

    # Description:
    # Sets the current hue and redraws the widget.
    # "self" HueBar widget instance.
    # "hue" Normalized hue value.
    def set_hue(self, hue: float):
        self.hue = max(0.0, min(1.0, hue))
        self.queue_draw()

    # Description:
    # Converts a Y position into a hue value.
    # "self" HueBar widget instance.
    # "y" Pointer Y position.
    def _set_from_y(self, y: float):
        h = self.get_height()
        if h <= 1: return
        y = max(0, min(h - 1, y))
        self.hue = max(0.0, min(1.0, y / (h - 1)))
        self.queue_draw()
        self.on_changed()

    # Description:
    # Handles click input on the hue bar.
    # "self" HueBar widget instance.
    # "gesture" GTK click gesture.
    # "n_press" Click count.
    # "x" Pointer X position.
    # "y" Pointer Y position.
    def on_press(self, gesture, n_press, x, y): 
        self.grab_focus() 
        self._set_from_y(y)
    # Description:
    # Stores drag start and updates hue immediately.
    # "self" HueBar widget instance.
    # "gesture" GTK drag gesture.
    # "x" Pointer X position.
    # "y" Pointer Y position.
    def on_drag_begin(self, gesture, x, y): 
        self._drag_start_y = y
        self._set_from_y(y)
    # Description:
    # Updates hue while dragging.
    # "self" HueBar widget instance.
    # "gesture" GTK drag gesture.
    # "offset_x" Horizontal drag offset.
    # "offset_y" Vertical drag offset.
    def on_drag_update(self, gesture, offset_x, offset_y): 
        self._set_from_y(self._drag_start_y + offset_y)

# Description:
# Main color picker square for saturation and brightness, because one slider was not enough.
class ColorSquare(Gtk.DrawingArea):
    # Description:
    # Builds the color square widget and hooks up pointer input.
    # "self" ColorSquare widget instance.
    # "on_changed" Callback fired after the color position changes.
    def __init__(self, on_changed):
        super().__init__()
        self.set_focusable(True) 
        self.set_content_width(300)
        self.set_content_height(300)
        self.hue = 0.0
        self.x_pos = 0.0 
        self.y_pos = 0.0 
        self.on_changed = on_changed
        self.set_draw_func(self.do_draw)
        click = Gtk.GestureClick()
        click.connect("pressed", self.on_press)
        self.add_controller(click)
        drag = Gtk.GestureDrag()
        drag.connect("drag-begin", self.on_drag_begin)
        drag.connect("drag-update", self.on_drag_update)
        self.add_controller(drag)

    # Description:
    # Updates the square hue background and redraws it.
    # "self" ColorSquare widget instance.
    # "hue" Normalized hue value.
    def set_hue(self, hue: float):
        self.hue = max(0.0, min(1.0, hue))
        self.queue_draw()

    # Description:
    # Sets the normalized picker position inside the square.
    # "self" ColorSquare widget instance.
    # "x" Normalized horizontal position.
    # "y" Normalized vertical position.
    def set_position(self, x: float, y: float):
        self.x_pos = max(0.0, min(1.0, x))
        self.y_pos = max(0.0, min(1.0, y))
        self.queue_draw()

    # Description:
    # Draws the color square and current picker position.
    # "self" ColorSquare widget instance.
    # "area" Drawing area argument from GTK.
    # "cr" Cairo drawing context.
    # "width" Current drawing width.
    # "height" Current drawing height.
    def do_draw(self, area, cr, width, height):
        hr, hg, hb = colorsys.hsv_to_rgb(self.hue, 1.0, 1.0)
        for yi in range(height):
            y = yi / max(1, height - 1)
            for xi in range(width):
                x = xi / max(1, width - 1)
                r = (hr * x) * (1.0 - y) + y
                g = (hg * x) * (1.0 - y) + y
                b = (hb * x) * (1.0 - y) + y
                cr.set_source_rgb(r, g, b)
                cr.rectangle(xi, yi, 1, 1)
                cr.fill()
        cx, cy = self.x_pos * (width - 1), self.y_pos * (height - 1)
        cr.set_source_rgb(1, 1, 1)
        cr.arc(cx, cy, 7, 0, 2 * math.pi)
        cr.fill_preserve()
        cr.set_source_rgb(0.7, 0.7, 0.7)
        cr.stroke()

    # Description:
    # Converts pointer coordinates into square positions.
    # "self" ColorSquare widget instance.
    # "x" Pointer X position.
    # "y" Pointer Y position.
    def _set_from_xy(self, x: float, y: float):
        w, h = self.get_width(), self.get_height()
        if w <= 1 or h <= 1: return
        self.x_pos, self.y_pos = max(0.0, min(1.0, x / (w - 1))), max(0.0, min(1.0, y / (h - 1)))
        self.queue_draw()
        self.on_changed()

    # Description:
    # Handles click input on the color square.
    # "self" ColorSquare widget instance.
    # "gesture" GTK click gesture.
    # "n_press" Click count.
    # "x" Pointer X position.
    # "y" Pointer Y position.
    def on_press(self, gesture, n_press, x, y): 
        self.grab_focus() 
        self._set_from_xy(x, y)
    # Description:
    # Stores drag start and updates the picker immediately.
    # "self" ColorSquare widget instance.
    # "gesture" GTK drag gesture.
    # "x" Pointer X position.
    # "y" Pointer Y position.
    def on_drag_begin(self, gesture, x, y):
        self._drag_start_x, self._drag_start_y = x, y
        self._set_from_xy(x, y)
    # Description:
    # Updates picker position while dragging.
    # "self" ColorSquare widget instance.
    # "gesture" GTK drag gesture.
    # "offset_x" Horizontal drag offset.
    # "offset_y" Vertical drag offset.
    def on_drag_update(self, gesture, offset_x, offset_y):
        self._set_from_xy(self._drag_start_x + offset_x, self._drag_start_y + offset_y)

# Description:
# Main application window tying the whole LED circus together.
class Window(Adw.ApplicationWindow):
    # Description:
    # Builds the main window and all UI controls.
    # "self" Window instance.
    # "app" Application instance owning this window.
    def __init__(self, app: Adw.Application):
        super().__init__(application=app)
        self.set_default_size(360, 500)
        self.set_resizable(False)
        self.set_icon_name("preferences-desktop-keyboard")

        self.live_timeout_id = None
        self.effects = backend.list_effects()
        self.state = load_state()
        self.saved_state = load_state()

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=WINDOW_TITLE))
        toolbar.add_top_bar(header)
        self.set_content(toolbar)

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        root.set_margin_top(12)
        root.set_margin_bottom(12)
        root.set_margin_start(12)
        root.set_margin_end(12)
        toolbar.set_content(root)

        bg_click = Gtk.GestureClick()
        bg_click.connect("pressed", lambda *args: self.grab_focus())
        root.add_controller(bg_click)

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        root.append(top)

        self.live_toggle = Gtk.ToggleButton(icon_name="media-playback-start-symbolic")
        self.live_toggle.set_active(True)
        self.live_toggle.connect("toggled", self.on_live_toggled)
        top.append(self.live_toggle)

        self.preview = Gtk.DrawingArea()
        self.preview.set_content_width(80)
        self.preview.set_content_height(28)
        self.preview.set_hexpand(True)
        top.append(self.preview)

        self.hex_entry = Gtk.Entry()
        self.hex_entry.set_width_chars(8)
        self.hex_entry.connect("activate", self.on_hex_activate)
        self.hex_entry.connect("changed", self.on_hex_changed)
        self.hex_entry.connect("notify::has-focus", self.on_hex_focus_changed) 
        top.append(self.hex_entry)

        center = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        root.append(center)

        self.hue_bar = HueBar(self.on_picker_changed)
        self.hue_bar.set_hue(self.state.hue)
        center.append(self.hue_bar)

        self.square = ColorSquare(self.on_picker_changed)
        self.square.set_hue(self.state.hue)
        self.square.set_position(self.state.x, self.state.y)
        center.append(self.square)

        self.effect_dropdown = Gtk.DropDown.new_from_strings(self.effects)
        if self.state.effect in self.effects:
            current_idx = self.effects.index(self.state.effect)
            self.effect_dropdown.set_selected(current_idx)

        self.effect_dropdown.connect("notify::selected", self.on_effect_changed)
        root.append(self.effect_dropdown)

        button_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        cancel_btn = Gtk.Button(label="Cancel")
        cancel_btn.connect("clicked", self.on_restore_clicked)
        
        self.apply_btn = Gtk.Button(label="Apply")
        self.apply_btn.add_css_class("suggested-action")
        self.apply_btn.set_hexpand(True)
        self.apply_btn.connect("clicked", self.on_apply_clicked)
        
        button_row.append(cancel_btn)
        button_row.append(self.apply_btn)
        root.append(button_row)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)
            
        self._update_apply_button_label()
        self.refresh_preview()

    # Description:
    # Returns the currently selected color as RGB.
    # "self" Window instance.
    def current_rgb(self) -> tuple[int, int, int]:
        return color_from_picker(self.hue_bar.hue, self.square.x_pos, self.square.y_pos)

    # Description:
    # Refreshes the color preview and hex field.
    # "self" Window instance.
    def refresh_preview(self):
        r, g, b = self.current_rgb()
        color_hex = rgb_to_hex(r, g, b)
        if not self.hex_entry.has_focus():
            if self.hex_entry.get_text() != color_hex:
                self.hex_entry.set_text(color_hex)
            self.hex_entry.set_position(-1)

        # Description:
        # Draws the little preview block. Tiny rectangle, huge responsibility.
        # "area" Drawing area argument from GTK.
        # "cr" Cairo drawing context.
        # "width" Current drawing width.
        # "height" Current drawing height.
        def draw_preview(area, cr, width, height):
            rgba = Gdk.RGBA()
            rgba.parse(color_hex)
            cr.set_source_rgba(rgba.red, rgba.green, rgba.blue, 1)
            cr.rectangle(0, 0, width, height); cr.fill()

        self.preview.set_draw_func(draw_preview)
        self.preview.queue_draw()

    # Description:
    # Handles updates coming from the hue bar or color square.
    # "self" Window instance.
    def on_picker_changed(self):
        self.square.set_hue(self.hue_bar.hue)
        self.refresh_preview()
        if self.live_toggle.get_active(): self.apply_live()

    # Description:
    # Handles effect dropdown changes.
    # "self" Window instance.
    # "dropdown" Effect dropdown widget.
    # "_param" Unused GTK notify parameter.
    def on_effect_changed(self, dropdown, _param):
        self._update_apply_button_label()
        if self.live_toggle.get_active(): GLib.idle_add(self._apply_live_now)

    # Description:
    # Updates the Apply button label based on the selected effect.
    # "self" Window instance.
    def _update_apply_button_label(self):
        effect = self.effects[self.effect_dropdown.get_selected()]
        if effect.split(".", 1)[0] == "0":
            self.apply_btn.set_label("Remove setting")
        else:
            self.apply_btn.set_label("Apply")

    # Description:
    # Filters hex input so the entry does not turn into nonsense.
    # "self" Window instance.
    # "entry" Hex entry widget.
    def on_hex_changed(self, entry: Gtk.Entry):
        if getattr(self, "_hex_filtering", False): return
        self._hex_filtering = True
        old_text = entry.get_text()
        new_text = ""
        for char in old_text:
            if char == '#' and new_text == "": new_text += char
            elif char.upper() in "0123456789ABCDEF": new_text += char.upper()
        max_length = 7 if new_text.startswith("#") else 6
        new_text = new_text[:max_length]
        if old_text != new_text:
            pos = entry.get_position()
            entry.set_text(new_text)
            new_pos = max(0, pos - (len(old_text) - len(new_text)))
            entry.set_position(new_pos)
        self._hex_filtering = False

    # Description:
    # Restores the current color in the hex entry when focus leaves it.
    # "self" Window instance.
    # "entry" Hex entry widget.
    # "param" Unused GTK notify parameter.
    def on_hex_focus_changed(self, entry, param):
        if not entry.has_focus():
            r, g, b = self.current_rgb()
            color_hex = rgb_to_hex(r, g, b)
            if entry.get_text() != color_hex: entry.set_text(color_hex)
            entry.set_position(-1)

    # Description:
    # Parses a typed hex color and updates the pickers.
    # "self" Window instance.
    # "entry" Hex entry widget.
    def on_hex_activate(self, entry: Gtk.Entry):
        rgb = hex_to_rgb(entry.get_text())
        if rgb:
            hue, x, y = rgb_to_picker(*rgb)
            self.hue_bar.set_hue(hue)
            self.square.set_hue(hue)
            self.square.set_position(x, y)
            self.refresh_preview()
            if self.live_toggle.get_active(): GLib.idle_add(self._apply_live_now)
        self.grab_focus() 

    # Description:
    # Schedules a short delayed live update.
    # "self" Window instance.
    def apply_live(self):
        if self.live_timeout_id: GLib.source_remove(self.live_timeout_id)
        self.live_timeout_id = GLib.timeout_add(20, self._apply_live_now)

    # Description:
    # Applies the current color or effect immediately.
    # "self" Window instance.
    def _apply_live_now(self):
        r, g, b = self.current_rgb()
        effect = self.effects[self.effect_dropdown.get_selected()]
        eff_id = effect.split(".", 1)[0]
        if eff_id == "0": backend.apply_off()
        elif eff_id == "1": backend.apply_direct(r, g, b)
        else:
            h, s, v = rgb_to_effect_params(r, g, b)
            backend.apply_effect(eff_id, h, s, v)
        self.live_timeout_id = None
        return False

    # Description:
    # Saves the current state and writes session restore settings.
    # "self" Window instance.
    # "_btn" Clicked button, ignored on purpose.
    def on_apply_clicked(self, _btn):
        self._apply_live_now()
        eff = self.effects[self.effect_dropdown.get_selected()]
        eff_id = eff.split(".", 1)[0]
        self.state = AppState(self.hue_bar.hue, self.square.x_pos, self.square.y_pos, eff)
        self.saved_state = self.state
        if eff_id == "0":
            if CONFIG_FILE.exists(): CONFIG_FILE.unlink()
            remove_systemd_service()
        else:
            save_state(self.state)
            script_exec = INSTALL_PATH if os.path.exists(INSTALL_PATH) else os.path.abspath(__file__)
            write_systemd_service(script_exec)
        self.close()

    # Description:
    # Handles keyboard shortcuts for effect changes and escape.
    # "self" Window instance.
    # "ctrl" Key controller.
    # "keyval" Pressed key value.
    # "keycode" Hardware keycode.
    # "state" Modifier state.
    def on_key_pressed(self, ctrl, keyval, keycode, state):
        if keyval == Gdk.KEY_Up: self.change_effect(-1); return True
        if keyval == Gdk.KEY_Down: self.change_effect(1); return True
        if keyval == Gdk.KEY_Escape: self.on_restore_clicked(None); return True
        return False

    # Description:
    # Restores the last saved state and applies it.
    # "self" Window instance.
    # "_btn" Clicked button, ignored on purpose.
    def on_restore_clicked(self, _btn):
        s = self.saved_state
        self.hue_bar.set_hue(s.hue); self.square.set_hue(s.hue); self.square.set_position(s.x, s.y)
        if s.effect in self.effects: self.effect_dropdown.set_selected(self.effects.index(s.effect))
        self.refresh_preview()
        self._apply_live_now()

    # Description:
    # Moves the selected effect up or down in the list.
    # "self" Window instance.
    # "direction" Relative dropdown direction.
    def change_effect(self, direction):
        idx = self.effect_dropdown.get_selected()
        new_idx = max(0, min(len(self.effects) - 1, idx + direction))
        if new_idx != idx: self.effect_dropdown.set_selected(new_idx)

    # Description:
    # Applies the current state when live mode gets enabled.
    # "self" Window instance.
    # "toggle" Live toggle button.
    def on_live_toggled(self, toggle):
        if toggle.get_active(): self._apply_live_now()

    # Description:
    # Restores saved state before the window closes.
    # "self" Window instance.
    def do_close_request(self):
        self.on_restore_clicked(None)
        return False

# Description:
# Small Adwaita app wrapper that starts the window and gets out of the way.
class App(Adw.Application):
    # Description:
    # Initializes the application with its ID and flags.
    # "self" Application instance.
    def __init__(self):
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.NON_UNIQUE)
        Adw.init()
    # Description:
    # Creates and presents the main window.
    # "self" Application instance.
    def do_activate(self):
        Window(self).present()

# --- HELPER FUNCTIONS ---

# Description:
# Clamps a numeric value to the allowed range.
# "v" Input value.
# "low" Minimum allowed value.
# "high" Maximum allowed value.
def clamp(v: float | int, low: int = 0, high: int = 255) -> int:
    return max(low, min(high, int(round(v))))

# Description:
# Converts RGB values to a hex color string.
# "r" Red channel value.
# "g" Green channel value.
# "b" Blue channel value.
def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02X}{g:02X}{b:02X}"

# Description:
# Converts a hex color string to RGB values.
# "text" Hex color text.
def hex_to_rgb(text: str) -> tuple[int, int, int] | None:
    text = text.strip()
    if text.startswith("#"): text = text[1:]
    if len(text) != 6: return None
    try: return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)
    except ValueError: return None

# Description:
# Saves the current app state to the config file.
# "state" State object to store.
def save_state(state: AppState) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps({
        "hue": state.hue, "x": state.x, "y": state.y, "effect": state.effect,
    }), encoding="utf-8")

# Description:
# Loads saved state from disk, or defaults if reality disagrees.
def load_state() -> AppState:
    if not CONFIG_FILE.exists(): return AppState()
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        saved_hue = float(data.get("hue", 0.0))
        if saved_hue > 1.0: saved_hue /= 255.0
        return AppState(
            hue=max(0.0, min(1.0, saved_hue)),
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            effect=str(data.get("effect", "1. Direct")),
        )
    except Exception: return AppState()

# --- SYSTEMD FUNCTIONS ---
# Description:
# Writes and enables the user systemd service for session restore.
# "script_path" Path to this script.
def write_systemd_service(script_path: str) -> None:
    systemd_dir = Path(GLib.get_home_dir()) / ".config" / "systemd" / "user"
    systemd_dir.mkdir(parents=True, exist_ok=True)
    service_file = systemd_dir / "rpi500plus-led.service"

    # Absolute paden voor stabiliteit, sleep voor hardware initialisatie
    service_content = f"""[Unit]
Description=RPi 500+ LED Session Manager

[Service]
Type=oneshot
RemainAfterExit=true
ExecStartPre=/bin/sleep 2
ExecStart=/usr/bin/python3 "{script_path}" --restore
ExecStop=/usr/bin/rpi-keyboard-config effect Off

[Install]
WantedBy=default.target
"""
    service_file.write_text(service_content, encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "--user", "enable", "rpi500plus-led.service"], capture_output=True)
    
    # Forceer een start zodat hij direct actief is in de huidige sessie
    subprocess.run(["systemctl", "--user", "start", "rpi500plus-led.service"], capture_output=True)

# Description:
# Removes the user systemd service and cleans up after it.
def remove_systemd_service() -> None:
    subprocess.run(["systemctl", "--user", "disable", "--now", "rpi500plus-led.service"], capture_output=True)
    service_file = Path(GLib.get_home_dir()) / ".config" / "systemd" / "user" / "rpi500plus-led.service"
    if service_file.exists():
        service_file.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "--user", "reset-failed"], capture_output=True)

# Description:
# Converts picker coordinates to RGB values.
# "hue" Normalized hue value.
# "x" Normalized horizontal picker position.
# "y" Normalized vertical picker position.
def color_from_picker(hue: float, x: float, y: float) -> tuple[int, int, int]:
    hr, hg, hb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
    r = (hr * x) * (1.0 - y) + y
    g = (hg * x) * (1.0 - y) + y
    b = (hb * x) * (1.0 - y) + y
    return clamp(r * 255), clamp(g * 255), clamp(b * 255)

# Description:
# Converts RGB values back to picker coordinates.
# "r" Red channel value.
# "g" Green channel value.
# "b" Blue channel value.
def rgb_to_picker(r: int, g: int, b: int) -> tuple[float, float, float]:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    x = max(r, g, b) / 255.0
    y = 1.0 - s
    return h, max(0.0, min(1.0, x)), max(0.0, min(1.0, y))

# Description:
# Converts RGB values to backend effect parameters.
# "r" Red channel value.
# "g" Green channel value.
# "b" Blue channel value.
def rgb_to_effect_params(r: int, g: int, b: int) -> tuple[int, int, int]:
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return clamp(h * 255), clamp(s * 255), clamp(v * 255)

# Description:
# Handles --restore mode for login session recovery.
def restore_mode() -> bool:
    if "--restore" not in sys.argv: return False
    s = load_state()
    r, g, b = color_from_picker(s.hue, s.x, s.y)
    eff_id = s.effect.split(".", 1)[0]
    backend = Backend()
    if eff_id == "0": backend.apply_off()
    elif eff_id == "1": backend.apply_direct(r, g, b)
    else:
        h, s, v = rgb_to_effect_params(r, g, b)
        backend.apply_effect(eff_id, h, s, v)
    backend.flush()
    return True

# --- MAIN ENTRY POINT ---

if __name__ == "__main__":
    if restore_mode():
        sys.exit(0)
    backend = Backend()
    app = App()
    exit_code = app.run(None)
    backend.flush()
    sys.exit(exit_code)
