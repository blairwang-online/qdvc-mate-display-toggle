# MAINTENANCE.md

Technical reference for anyone (human or AI) maintaining
`display-switcher.py`. It assumes familiarity with Python; GTK and `xrandr`
specifics are explained where they matter.

---

## 1. What this program is

A single-file GTK 3 application (`display-switcher.py`) that presents a small
popup with four display-mode buttons and applies the chosen mode by shelling
out to `xrandr`. It is designed to be bound to a keyboard shortcut (Super+P)
on the MATE desktop, where no built-in display-switching popup exists.

There is no build step, no package, no dependencies beyond the system GTK 3
bindings and `xrandr`. You run the `.py` file directly.

---

## 2. Hard environmental assumptions

These are baked in. If any stops holding, the program needs rework:

- **X11, not Wayland.** Everything is driven by `xrandr`, which is an X11
  tool. Under Wayland it will either fail or operate on XWayland only. There
  is no Wayland code path. A Wayland port would mean replacing the entire
  `xrandr` layer (e.g. with `wlr-randr`, KScreen, or compositor-specific IPC).
- **`xrandr` is on `PATH`** and produces output in the conventional format
  (see §5). The parser is regex-based against that text format.
- **GTK 3** is available via PyGObject (`gi`). Not GTK 4 — several calls used
  here (notably `Gtk.Statusbar` internals, `Gtk.WindowType.TOPLEVEL`) differ
  or are gone in GTK 4. See §8 for the GTK-4 migration note.
- **Single internal panel.** The "internal vs external" split assumes one
  built-in laptop panel. Desktops with no internal panel still work but the
  internal/external semantics become whatever `pick_internal` guesses.

---

## 3. File layout / reading order

The file is organised top to bottom as: constants → `Mode` enum + `MODE_ORDER`
→ pure helper functions (`get_outputs`, `common_mode`, `pick_internal`,
`detect_current_mode`) → the action function (`apply_mode`) → the GTK window
class (`DisplayPopup`) → `main()`.

The helper functions are deliberately free of GTK so they can be tested
headlessly (see §7).

---

## 4. The `Mode` enum and `MODE_ORDER` (the extension point)

```python
class Mode(Enum):
    MIRROR        = 'Mirror'
    EXTEND        = 'Extend'
    EXTERNAL_ONLY = 'External Only'
    BUILTIN_ONLY  = 'Built-in Only'
```

Each member's **value is its user-facing label**, exposed via the `.label`
property. This is the single source of truth for wording — buttons, the status
bar, and the error dialog all read `mode.label`, so there is no duplicated
string to keep in sync.

```python
MODE_ORDER = [Mode.MIRROR, Mode.EXTEND, Mode.EXTERNAL_ONLY, Mode.BUILTIN_ONLY]
```

`MODE_ORDER` defines **the on-screen sequence and the 1–4 key bindings**. The
UI is built by iterating it, and the selected index is an index into it.
Consequences for maintainers:

- **To reorder the buttons:** rearrange `MODE_ORDER`. Nothing else changes.
  The number labels (1–4) are derived from list position, the number-key
  bindings map position → list index, and detection maps a `Mode` back to its
  position via `MODE_ORDER.index(...)`.
- **To rename a mode:** change the enum value. It updates everywhere.
- **To add a fifth mode:** add an enum member, add a branch in `apply_mode`,
  add it to `MODE_ORDER`, and **extend the `number_keys` map** in `on_key`
  (currently hardcoded for 1–4 only — see §6, this is the one place that does
  not auto-scale).
- **To remove a mode:** drop it from `MODE_ORDER` (and ideally the enum).
  The number-key handler guards with `if idx < len(MODE_ORDER)` so stale
  bindings are harmless.

---

## 5. `xrandr` parsing (`get_outputs`)

`get_outputs()` runs `xrandr --query` and returns four values:

| Return    | Type | Meaning |
|-----------|------|---------|
| `connected` | list[str] | Names of plugged-in outputs, in xrandr order |
| `primary`   | str | The primary output (or first connected as fallback) |
| `modes`     | dict[str, list[str]] | output → supported `"WxH"` strings |
| `geometry`  | dict[str, tuple\|None] | output → `(w, h, x, y)` if active, else `None` |

Parsing relies on the conventional `xrandr --query` text format:

- A **connected output** line looks like
  `HDMI-1 connected primary 1920x1080+1920+0 (normal ...) 530mm x 300mm`.
  - The leading token is the output name.
  - The word `connected` (vs `disconnected`) marks it as plugged in.
  - The optional `primary` keyword marks the primary.
  - **The `WxH+X+Y` blob only appears when the output is active** (has a mode
    set). This is the key signal used to tell "on" from "off". Captured via
    `re.search(r'(\d+)x(\d+)\+(\d+)\+(\d+)', line)`.
- **Mode lines** are indented and begin with a resolution, e.g.
  `   1920x1080     60.00*+`. The current/preferred markers (`*`, `+`) are
  ignored; only the `WxH` is captured.
- A `disconnected` line resets the "current output" context so stray mode
  lines are not misattributed.

**Fragility note:** this is text parsing of a human-oriented format. It has
held across typical `xrandr` versions, but a format change, an exotic output
name, or transform/rotation strings could in principle break a regex. If
detection misbehaves, dump `xrandr --query` and compare against the regexes
first. A more robust (but heavier) alternative would be the XRandR API via
`python-xlib` or parsing `xrandr --listmonitors`.

---

## 6. Current-mode detection (`detect_current_mode`)

Returns a `Mode` (not an index, not a string). Logic, in order:

1. No connected outputs → `EXTEND` (arbitrary safe default).
2. Only external(s) active, internal off → `EXTERNAL_ONLY`.
3. Only internal active, externals off → `BUILTIN_ONLY`.
4. Two or more active outputs: compare their **origins** `(x, y)`:
   - all share one origin (overlaid) → `MIRROR`
   - different origins (placed apart) → `EXTEND`
5. Exactly one active output: internal → `BUILTIN_ONLY`, else `EXTERNAL_ONLY`.

**Known heuristic limitation (Mirror vs Extend):** the discriminator is origin
position only. An unusual extended layout where a second display is manually
placed at the same `+0+0` origin would be misread as Mirror. Origin is the
most reliable signal available from `xrandr` text alone; requiring identical
resolution instead would misfire on genuine mirror setups across
different-sized panels. This is why the status bar explicitly frames the
result as a *best guess*. If you tighten this, update that wording too.

`pick_internal()` decides which output is the built-in panel by name prefix
(`eDP`, `LVDS`, `DSI`, case-insensitive), falling back to the first connected
output. If a machine names its internal panel differently, this is the
function to adjust (or hardcode).

---

## 7. Applying a mode (`apply_mode`)

Builds and runs a single `xrandr` command per mode:

- **MIRROR** — finds a resolution **all** outputs support via `common_mode()`
  and sets every output to that mode at `--pos 0x0`, with `--same-as` the
  first output. This shared-resolution step is essential: `--auto` alone
  picks each panel's *native* mode independently, and `xrandr` cannot overlay
  two different-sized framebuffers, so naive mirroring silently no-ops. If no
  common resolution exists, it falls back to `--auto` (which will likely fail,
  but now visibly — see error handling below).
- **EXTEND** — `--auto` each output and chain them left-to-right with
  `--right-of`.
- **EXTERNAL_ONLY** — `--auto` the external(s), `--off` the internal, primary
  on the first external. No-ops if there is no external.
- **BUILTIN_ONLY** — `--auto`/primary the internal, `--off` each external.

**Error surfacing:** the `xrandr` call uses `capture_output=True` and checks
the return code. On failure it shows a `Gtk.MessageDialog` containing stderr
and the exact command that was run. This was added deliberately because an
earlier version used a bare `subprocess.run` that swallowed failures, making
the broken Mirror mode look like it "did nothing." **Keep failures visible.**

---

## 8. The GTK UI (`DisplayPopup`)

Structure: a `TOPLEVEL` window → vertical `outer` box containing
(a) a centered horizontal `header` (icon + wrapped instruction label),
(b) a horizontal `box` of four mode buttons,
(c) a `Gtk.Statusbar`.

Points that have caused trouble before and should not be "cleaned up" without
understanding why they are the way they are:

- **`Gtk.WindowType.TOPLEVEL`, not `POPUP`.** An earlier `POPUP` window would
  not reliably grab keyboard focus, so the arrow keys did nothing. `TOPLEVEL`
  + `present()` fixes that and also gives the standard titlebar.
- **Header centering / label wrapping.** The instruction label wraps only
  because it is given a small *preferred* width via
  `set_max_width_chars(HEADER_TEXT_LABEL_SIZE)` **and** the header box is
  centered (`halign=CENTER`) so it does not stretch to the full window width.
  A pixel `set_size_request` alone did **not** force wrapping, because the
  label still advertised its full single-line natural width. If you change
  this, test that the text actually wraps; the two settings work together.
  - `HEADER_TEXT_LABEL_SIZE` (default 48) is the wrap width in characters —
    lower = narrower/taller text block.
  - `HEADER_SIDE_PADDING_PX` (default 60) is the left/right gap around the
    centered header.
- **Status bar italics.** `Gtk.Statusbar.push()` **escapes Pango markup**, so
  `<i>` tags pushed through it render literally. To get italic + centered
  text we reach into the statusbar's message area
  (`get_message_area().get_children()[0]`), which is the internal `Gtk.Label`,
  and call `set_markup()` on it directly. We do **not** use `push()` for
  display. This reaches into GTK internals; it is verified working on GTK
  3.24 but is the most likely thing to break on a GTK upgrade.
- **Highlighting = focus.** The "selected" button is indicated by calling
  `grab_focus()` on it (`update_highlight`). The visible highlight is the
  theme's focus ring. If a theme draws a weak focus ring, the selection may
  be hard to see; the fallback would be to style the selected button via a
  CSS provider instead.
- **Number-key map is hardcoded** in `on_key` for keys 1–4 (both top-row and
  keypad). This is the single place that does **not** auto-scale with
  `MODE_ORDER`. If the number of modes changes, update this map. It is
  guarded with `if idx < len(MODE_ORDER)` so extra entries are inert.

Activation paths: clicking a button (`on_button_clicked`) and Enter
(`activate_selected`) both call `apply_mode(MODE_ORDER[index])` then quit.
Arrow/Tab keys move `self.selected` and re-highlight without applying.

### GTK 4 migration note

If ever moving to GTK 4: `Gtk.WindowType` is gone (windows are created
differently), `Gtk.Statusbar` is removed entirely (replace the status line
with a plain `Gtk.Label`), container `pack_start` APIs change, and
`override_*`/some styling calls differ. The `xrandr`/detection layer is
GTK-agnostic and would carry over unchanged.

---

## 9. Testing without real hardware

The non-GTK helpers can be exercised headlessly by stubbing `xrandr`:

1. Put a fake `xrandr` shell script early on `PATH` that `cat`s a canned
   `xrandr --query` block for the scenario you want (extended, mirror,
   external-only, built-in-only, mirror-with-different-sizes).
2. Import the module and call `detect_current_mode()` / `get_outputs()`.

For the GUI itself, install GTK 3 bindings (`gir1.2-gtk-3.0`) and run under a
virtual X server: `xvfb-run -a python3 ...`. This lets you assert on widget
state (e.g. that the status label is a real `Gtk.Label`, that markup parses,
that the detected mode maps to the expected selected index) without a real
display. The Mirror-vs-Extend and on/off detection branches in particular are
worth a canned-output regression check after any parser change.

---

## 10. Quick change recipes

- **Reorder buttons:** edit `MODE_ORDER`.
- **Rename a mode everywhere:** edit the enum value.
- **Change internal-panel detection:** edit `pick_internal`.
- **Tune the Mirror-vs-Extend guess:** edit `detect_current_mode` (and the
  status-bar wording if you change its confidence).
- **Adjust header text width/wrap:** `HEADER_TEXT_LABEL_SIZE`.
- **Adjust header side whitespace:** `HEADER_SIDE_PADDING_PX`.
- **Add a mode:** enum member + `apply_mode` branch + `MODE_ORDER` entry +
  `number_keys` map.
