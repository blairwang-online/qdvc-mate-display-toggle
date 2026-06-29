#!/usr/bin/env python3
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk
import subprocess
import re


def get_outputs():
    """Return (connected_outputs, primary). Connected = plugged in."""
    out = subprocess.check_output(['xrandr', '--query']).decode()
    connected = []
    primary = None
    for line in out.splitlines():
        m = re.match(r'^(\S+)\s+connected\s*(primary)?', line)
        if m:
            connected.append(m.group(1))
            if m.group(2):
                primary = m.group(1)
    if primary is None and connected:
        primary = connected[0]
    return connected, primary


def pick_internal(connected):
    """Heuristic: internal panel is usually eDP/LVDS/DSI."""
    for name in connected:
        if re.match(r'(eDP|LVDS|DSI)', name, re.I):
            return name
    return connected[0] if connected else None


def apply_mode(mode):
    connected, primary = get_outputs()
    if len(connected) < 1:
        return
    internal = pick_internal(connected)
    externals = [o for o in connected if o != internal]

    cmd = ['xrandr']

    if mode == 'Mirror':
        # Mirror everything onto the internal (or first) output position.
        base = internal or connected[0]
        for o in connected:
            cmd += ['--output', o, '--auto', '--same-as', base]

    elif mode == 'Join Displays':
        prev = None
        for o in connected:
            cmd += ['--output', o, '--auto']
            if prev:
                cmd += ['--right-of', prev]
            prev = o

    elif mode == 'External Only':
        if not externals:
            return
        for o in externals:
            cmd += ['--output', o, '--auto']
        cmd += ['--output', internal, '--off']
        # primary on first external
        cmd += ['--output', externals[0], '--primary']

    elif mode == 'Built-in Only':
        cmd += ['--output', internal, '--auto', '--primary']
        for o in externals:
            cmd += ['--output', o, '--off']

    subprocess.run(cmd)


class DisplayPopup(Gtk.Window):
    MODES = ['Mirror', 'Join Displays', 'External Only', 'Built-in Only']

    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_position(Gtk.WindowPosition.CENTER_ALWAYS)
        self.set_decorated(False)
        self.set_keep_above(True)

        self.selected = 1  # default highlight "Join Displays"
        self.buttons = []

        frame = Gtk.Frame()
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        for i, mode in enumerate(self.MODES):
            lbl = Gtk.Label(label=mode)
            lbl.set_size_request(120, 80)
            eb = Gtk.EventBox()
            eb.add(lbl)
            self.buttons.append(eb)
            box.pack_start(eb, True, True, 0)

        frame.add(box)
        self.add(frame)

        self.connect('key-press-event', self.on_key)
        self.connect('focus-out-event', lambda *a: Gtk.main_quit())
        self.update_highlight()

    def update_highlight(self):
        for i, eb in enumerate(self.buttons):
            ctx = eb.get_style_context()
            if i == self.selected:
                eb.override_background_color(
                    Gtk.StateFlags.NORMAL, Gdk.RGBA(0.2, 0.5, 0.9, 1))
            else:
                eb.override_background_color(
                    Gtk.StateFlags.NORMAL, Gdk.RGBA(0, 0, 0, 0))

    def on_key(self, widget, event):
        key = event.keyval
        if key in (Gdk.KEY_Right, Gdk.KEY_Tab):
            self.selected = (self.selected + 1) % len(self.MODES)
            self.update_highlight()
        elif key == Gdk.KEY_Left:
            self.selected = (self.selected - 1) % len(self.MODES)
            self.update_highlight()
        elif key in (Gdk.KEY_Return, Gdk.KEY_KP_Enter):
            mode = self.MODES[self.selected]
            self.hide()
            apply_mode(mode)
            Gtk.main_quit()
        elif key == Gdk.KEY_Escape:
            Gtk.main_quit()
        return True


def main():
    win = DisplayPopup()
    win.show_all()
    win.grab_focus()
    # Ensure keyboard focus on a POPUP window.
    win.get_window().focus(Gdk.CURRENT_TIME)
    Gtk.main()


if __name__ == '__main__':
    main()
