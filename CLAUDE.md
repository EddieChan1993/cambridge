# Cambridge — Project Guide for Claude

## What This Is

A macOS menu-bar dictionary app that looks up words on Cambridge Dictionary.
Built with Python 3 + PyObjC (native AppKit UI). No Electron, no web views.

## Architecture

```
main.py               Entry point — creates NSApplication, sets activation policy
app_delegate.py       NSApplicationDelegate — wires everything together
main_window.py        Main NSWindow (split view: word list + word display)
float_panel.py        Floating NSPanel for future hotkey-triggered popups
hotkey_monitor.py     Global hotkey via CGEventTap (fallback: NSEvent monitor)
settings.py           Settings persistence (~/.cambridge_tool/settings.json)
settings_window.py    Hotkey settings UI with recorder + conflict detection
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
- Autoresizing masks: `2` = width sizable, `4` = right margin flexible, `8` = bottom margin flexible (pin to top), `16` = height sizable.

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
| `settings.json` | `{hotkey_keycode, hotkey_modifiers}` |
| `app.pid` | PID of running instance (single-instance guard) |

## Scraper Data Format

`scrape_cambridge(word)` returns:

```python
{
  "word": str,
  "url": str,
  "pronunciations": [{"label": "uk"|"us", "ipa": str}],
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

## Settings / Hotkey

- Default hotkey: `⌘⇧C` (keycode 8, modifiers `["cmd", "shift"]`)
- Modifier names: `"cmd"`, `"shift"`, `"alt"`, `"ctrl"`
- Change via right-click status bar icon → 偏好设置…
- `settings.py` maps keycodes to display chars (`KEYCODE_NAMES`) and detects conflicts (`SYSTEM_CONFLICTS`)

When the hotkey fires:
1. Simulates `Cmd+C` to copy selected text from the frontmost app
2. Shows the main window (`orderFrontRegardless`)
3. Looks up the word in the main window

## Dependencies

```
pyobjc-core / pyobjc-framework-Cocoa / pyobjc-framework-Quartz
requests, beautifulsoup4, lxml   — scraping
openpyxl                         — favorites XLSX export
py2app                           — packaging
```

Python 3.9+ required. Anaconda Python is explicitly excluded by `build.sh` due to PyObjC incompatibilities.
