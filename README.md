# qdvc-mate-display-toggle

A quick display-mode switcher for the **MATE** desktop, filling the gap left by
the absence of a GNOME/Windows-style **Super+P** display popup.

Press your shortcut, pick a mode, done:

| # | Mode          | Effect                                            |
|---|---------------|---------------------------------------------------|
| 1 | Mirror        | Same image on every display                       |
| 2 | Extend        | Displays joined side by side                      |
| 3 | External Only | Built-in panel off, external display(s) on        |
| 4 | Built-in Only | External display(s) off, built-in panel on        |

On launch it auto-detects your current arrangement (best guess) and highlights
the matching option.

## Usage

```bash
python3 display-switcher.py
```

- **Arrow keys** or number keys **1–4** move the highlight, **Enter** applies.
- Or just **click** an option.
- **Esc** cancels.

Bind `python3 /path/to/display-switcher.py` to **Super+P** in
*System → Preferences → Hardware → Keyboard Shortcuts* for the full experience.

## Requirements

- Linux running **X11** (not Wayland)
- `xrandr`
- Python 3 with **GTK 3** bindings (`python3-gi`, `gir1.2-gtk-3.0`)

## How it works

A single GTK 3 script that drives `xrandr`. See
[`MAINTENANCE.md`](MAINTENANCE.md) for the technical details.
