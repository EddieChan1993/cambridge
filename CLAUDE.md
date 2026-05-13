# Cambridge — Project Guide for Claude

## What This Is

A macOS menu-bar dictionary app that looks up words on Cambridge Dictionary.
Built with Python 3 + PyObjC (native AppKit UI). No Electron, no web views.

## Architecture

```
main.py               Entry point — creates NSApplication, sets activation policy
app_delegate.py       NSApplicationDelegate — wires everything together
main_window.py        Main NSWindow (sidebar + word display)
float_panel.py        Floating NSPanel for hotkey-triggered popups
hotkey_monitor.py     Global hotkey via CGEventTap (fallback: NSEvent monitor)
settings.py           Settings persistence (~/.cambridge_tool/settings.json)
settings_window.py    Preferences UI: hotkey recorder + URL + sidebar toggle
scraper.py            Cambridge Dictionary scraper (requests + BeautifulSoup4)
word_display.py       NSTextView rich-text renderer for dictionary entries
data_manager.py       JSON persistence: history, favorites, cache
utils.py              run_on_main_thread() helper
setup.py              py2app packaging config
build.sh              Build script (supports --dev alias mode)
```

## Key Conventions

### PyObjC Method Naming
- All non-ObjC helper methods on `NSObject` subclasses **must** be decorated with `@objc.python_method` — otherwise PyObjC registers them as ObjC selectors and crashes with `BadPrototypeError`.
- IBAction methods use trailing underscore: `def searchBtnClick_(self, sender):` → ObjC selector `searchBtnClick:`.
- Multi-argument ObjC methods: `def initWithDelegate_keycode_modifiers_(self, d, k, m):` → selector `initWithDelegate:keycode:modifiers:`.
- Never name a method `save_` — conflicts with internal ObjC. Use specific names like `saveSettings_`.

### NSView Coordinate System
- macOS uses **bottom-left origin** (y=0 is bottom). Pin controls to the top by giving them a small `MinYMargin` (flexible bottom margin = autoresizing mask bit 8).
- Autoresizing masks: `1` = left margin flexible, `2` = width sizable, `4` = right margin flexible, `8` = bottom margin flexible (pin to top), `16` = height sizable, `32` = top margin flexible (pin to bottom).

### Window Showing (LSUIElement apps)
- Use `window.orderFrontRegardless()` instead of `makeKeyAndOrderFront_` for menu-bar accessory apps — more reliable when the app is not the active process.
- Always call `NSApplication.sharedApplication().activateIgnoringOtherApps_(True)` before showing a window.

### NSTrackingArea Options
- `NSTrackingMouseEnteredAndExited` = `0x01`
- `NSTrackingActiveAlways` = `0x80`
- Correct options: `0x01 | 0x80 = 0x81`. **Do not use** `0x02` (that is `NSTrackingMouseMoved`, not `NSTrackingActiveAlways`).

### Copy/Paste in Text Fields
- Requires a main menu with an Edit submenu whose items target `nil` (first responder).
- Set up in `app_delegate._buildMainMenu()`. Do not remove this.

### NSMakeRect
- `NSMakeRect` is a C inline function — **cannot be imported from Foundation**.
- Use Python tuples `(x, y, width, height)` instead; PyObjC converts them automatically to NSRect.

## Build

```bash
# Fast dev build (symlinks, local-only, seconds)
bash build.sh --dev

# Full distributable build
bash build.sh
```

`build.sh` automatically:
1. Kills any running old instance (PID file + `pkill`)
2. Clears the word cache (`~/.cambridge_tool/cache.json`)
3. Detects Python 3.9+ (skips Anaconda/miniforge)
4. Skips `pip install` if `requirements.txt` hasn't changed (MD5 hash flag)
5. Converts `icon.png` → `icon.icns` if changed
6. Builds with py2app, filters signature noise from output

## Data Storage

All data lives in `~/.cambridge_tool/`:

| File | Content |
|------|---------|
| `history.json` | `[{word, time}, ...]` — last 200 words |
| `favorites.json` | `{word_lower: {word, data, time}, ...}` |
| `cache.json` | `{word_lower: {cached_at, data}, ...}` — 7-day TTL |
| `settings.json` | persistent preferences (hotkey, URL, sidebar state, …) |
| `app.pid` | PID of running instance (single-instance guard) |

## Scraper Data Format

`scrape_cambridge(word, base_url="")` returns:

```python
{
  "word": str,
  "url": str,
  "pronunciations": [{"label": "uk"|"us", "ipa": str, "audio": str}],  # audio = full MP3 URL
  "entries": [
    {
      "pos": str,           # "noun", "verb", etc.
      "pos_gram": str,      # "[ C or U ]" — entry-level grammar
      "definitions": [
        {
          "en": str,        # English definition
          "zh": str,        # Chinese translation
          "gram": str,      # "[ T ]", "[ U ]" — per-definition grammar
          "label": str,     # "informal", "literary", etc.
          "usage": str,     # "not usually before noun"
          "examples": [{"en": str, "zh": str}]
        }
      ]
    }
  ],
  "error": str              # present only on failure
}
```

### Audio URL extraction
Cambridge audio `<source src="...">` uses **relative paths** like `/zhs/media/英语-汉语-繁体/uk_pron/...mp3`.
Must prepend `https://dictionary.cambridge.org` to get a valid URL.
The `<audio>` tag lives inside `.daud` which is a **sibling** of `.ipa`, both inside `.dpron-i`.
Walk up from `.ipa` to find `.dpron-i`, then search inside for `.daud > audio > source[type="audio/mpeg"]`.

## Settings / Hotkey

- Default lookup hotkey: `⌘⇧C` (keycode 8, modifiers `["cmd", "shift"]`)
- Default show-window hotkey: `⌘⌥Space` (keycode 49, modifiers `["cmd", "alt"]`)
- Modifier names: `"cmd"`, `"shift"`, `"alt"`, `"ctrl"`
- Change via right-click status bar icon → 偏好设置…
- `settings.py` maps keycodes to display chars (`KEYCODE_NAMES`) and detects conflicts (`SYSTEM_CONFLICTS`)
- Settings keys: `hotkey_keycode`, `hotkey_modifiers`, `show_window_keycode`, `show_window_modifiers`, `lookup_base_url`, `sidebar_open_on_start`

When the lookup hotkey fires:
1. Simulates `Cmd+C` to copy selected text from the frontmost app
2. Shows the main window (`orderFrontRegardless`)
3. Looks up the word in the main window

## Layout — main_window.py

Sidebar is on the **right**; content area is on the **left**. No NSSplitView — plain NSView layout with autoresizing masks.

```
content view (full window)
├── right (content area)  x=0, mask=2|16
│   ├── hdr               top bar, mask=2|8
│   ├── div               1px separator below hdr, mask=2|8
│   ├── pron_bar          UK/US audio buttons (30px, hidden when no audio), mask=2|8
│   ├── scroll_content    word display, mask=2|16
│   └── overlay           centered error state, mask=2|16
├── sep_main              1px vertical divider, mask=1|16
└── left (sidebar)        历史/收藏, x=cw-LEFT_W, mask=1|16
```

- Sidebar defaults to **hidden** on startup; toggle via ☰ button in header right side.
- `settings.sidebar_open_on_start` is read on **first** `showWindow()` call only (`_first_shown` flag).
- `PRON_BAR_H = 30` — pron bar sits between divider and scroll content; hidden when word has no audio.

## Word Display — word_display.py

- **POS divider**: repeated `─` characters with `boldSystemFontOfSize_(10)`, yellow color, `NSLineBreakByClipping`, `tailIndent=-32` (accounts for scrollbar overlay on right).
- **Numbering**: skipped when a POS section has only one definition (`len(defs) == 1`).
- **Deduplication**: `usage` field not shown as `▸ line` if already present in inline `gram`/`label` notes.
- **Example sentences**: italic via `NSFontManager.convertFont_toHaveTrait_(font, 1)` (NSItalicFontMask=1).
- **Full-width separator pitfalls**:
  - `NSBackgroundColorAttributeName` on `\n` does NOT render a full-width background — only covers the glyph width (zero for `\n`).
  - `NSTextAttachment` subclass approach works in theory but is fragile in PyObjC — avoid.
  - **Simplest reliable approach**: repeated `─` + `NSLineBreakByClipping`.

## Status Bar

- Icon: `"C"` (bold, size 14)
- Left-click: intercept in `menuWillOpen_`, cancel tracking, `setHighlighted_(True)`, show window, reset highlight after 0.15s via `performSelector_withObject_afterDelay_`.
- Right-click: standard NSMenu with 偏好设置 and 退出.

## Preferences Window — settings_window.py

- Section 1: 划词查询快捷键 (record button)
- Section 2: 呼出主界面快捷键 (record button)
- Section 3: 查询接口地址 — URL field **auto-saves on blur** (`controlTextDidEndEditing_`); 恢复默认 saves immediately.
- Section 4: 侧边栏默认状态 — checkbox **auto-saves on toggle** (`toggleSidebarDefault_`).
- Cancel/Save buttons only affect hotkey settings.

## Known Pitfalls

- **NSSplitView + window state restoration**: macOS overrides `setPosition_ofDividerAtIndex_` via saved state even with `setRestorable_(False)`. Solution: remove NSSplitView entirely and use plain NSView layout.
- **History for non-existent words**: only call `add_history` / `set_cached` when `has_entries` is True.
- **`NSMakeRect` import**: cannot import from Foundation — use tuples.
- **Status bar click highlight**: `menuWillOpen_` + `cancelTracking()` removes the system highlight; must manually call `setHighlighted_(True)` and schedule reset.

## Global Hotkey — Lessons Learned (hard-won)

### Why CGEventTap / NSEvent monitor silently fail in py2app --dev builds

Both `CGEventTapCreate` and `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_`
require macOS TCC permissions (Accessibility and Input Monitoring respectively).
**Each `--dev` rebuild changes the executable's code signature**, which silently
invalidates the previously granted permission. Symptom: tap returns `None`, monitor
registers successfully but handler is never called — no error, no crash.

**Fix after any rebuild that changes the binary:**
```bash
tccutil reset Accessibility com.local.hotdict
tccutil reset ListenEvent com.local.hotdict
```
Then relaunch the app — it will re-prompt for Accessibility; grant it, then manually
enable Input Monitoring in System Settings → Privacy & Security → Input Monitoring.

### HotkeyMonitor must be a plain Python class, not NSObject

Using `NSObject` as the base class for `HotkeyMonitor` caused PyObjC to silently
swallow exceptions inside `initWithDelegate_keycode_modifiers_` (the ObjC bridge
catches them and returns `nil`), preventing `_register` from ever running.
**Solution**: use a plain Python `class HotkeyMonitor:` with `__init__`, and update
call sites in `app_delegate.py` from `HotkeyMonitor.alloc().initWith...()` to
`HotkeyMonitor(delegate, keycode, modifiers)`.

### Defer hotkey registration until the run loop is running

`CGEventTapCreate` and `CFRunLoopAddSource` must be called after `NSApplication`
has started its run loop. Calling them directly in `__init__` (which runs during
`applicationDidFinishLaunching_`) is safe, but any Carbon APIs (e.g.
`GetApplicationEventTarget`) will segfault at that point.
Use `run_on_main_thread(lambda: self._start())` to defer if needed.

### GC will collect Python callbacks passed to C APIs

`CGEventTapCreate` takes a Python closure as callback. The Quartz C layer holds a
C-level pointer — Python's GC does not see it and will collect the closure.
**Always store callbacks as instance attributes:**
```python
self._tap_cb  = _cb   # prevent GC of CGEventTap callback
self._tap_src = src   # prevent GC of CFRunLoopSource
```
Same applies to `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_`:
```python
self._ns_handler = _handler   # prevent GC
```

### Carbon RegisterEventHotKey does NOT work in this AppKit + py2app context

`GetApplicationEventTarget()` segfaults — the Carbon Event Manager is not
initialised in a pure AppKit run loop. Do not attempt Carbon hotkey registration.
Stick with CGEventTap (active, requires Accessibility) + NSEvent global monitor
fallback (passive, requires Input Monitoring).

### _log / file I/O: always specify encoding="utf-8"

`open()` without encoding defaults to ASCII on some locales. Any Unicode character
in a format string (e.g. `→`) will raise `UnicodeEncodeError`, which — if inside
a `try/except Exception` block inside the CGEventTap callback — silently causes the
callback to return the event unmodified instead of consuming it.
```python
# correct
with open("/tmp/hotdict_init.log", "a", encoding="utf-8") as f:
```

### Hotkey lookup order: get selected text BEFORE stealing focus

`hotkeyTriggered` must call `_getSelectedText()` **before** `showWindow()`.
`showWindow()` activates HotDict, so any simulated `Cmd+C` sent afterwards goes to
HotDict itself, not the source app.

### Run _getSelectedText on a background thread

`_getSelectedText` calls `time.sleep(0.15)` to wait for the clipboard.  Calling
this on the main thread blocks the CGEventTap callback loop; macOS detects the
stall, plays the system alert sound (beep), and may disable the tap.
**Solution**: run `_getSelectedText` in a `threading.Thread`, then dispatch
`showWindow` + `lookupWordInMainWindow_` back to the main thread via
`run_on_main_thread`.

### Debugging stdout is invisible in py2app builds

`print()` goes to the app's stdout which is swallowed by py2app (even in `--dev`
mode). `log stream --predicate 'process == "HotDict"'` only shows `os_log` /
`NSLog` output. **Use file logging for all diagnostics:**
```python
with open("/tmp/hotdict_init.log", "a", encoding="utf-8") as f:
    f.write(msg + "\n")
```

## Dependencies

```
pyobjc-core / pyobjc-framework-Cocoa / pyobjc-framework-Quartz
requests, beautifulsoup4, lxml   — scraping
openpyxl                         — favorites XLSX export
py2app                           — packaging
```

Python 3.9+ required. Anaconda Python is explicitly excluded by `build.sh` due to PyObjC incompatibilities.
