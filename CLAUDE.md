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
settings_window.py    Preferences UI: hotkey recorder + URL + sidebar toggle + sync path
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
5. If `icon.png` is absent, renders it from `logo.svg` via `qlmanage` (`icon.png` is gitignored — `logo.svg` is the source of truth)
6. Converts `icon.png` → `icon.icns` if changed (MD5 cache flag)
7. Builds with py2app, filters signature noise from output
8. **Full build only**: runs `tccutil reset Accessibility/ListenEvent` and prints permission reminder

## Data Storage

`~/.cambridge_tool/` always exists and holds cache, settings, and PID:

| File | Content |
|------|---------|
| `cache.json` | `{word_lower: {cached_at, data}, ...}` — 7-day TTL, always local |
| `settings.json` | persistent preferences (hotkey, URL, sidebar state, sync path, …) |
| `app.pid` | PID of running instance (single-instance guard) |

`history.json` and `favorites.json` live in the **active data directory**:
- Default: `~/.cambridge_tool/`
- If `settings.sync_data_path` is set: `<sync_data_path>/HotDict/` (subfolder prevents cluttering cloud root)

`DataManager` manages the active directory:
- `__init__(sync_dir="")` — pass `settings.sync_data_path` on startup
- `set_sync_dir(path)` — switch directory live and reload history/favorites
- `migrate_local_to_path(dest)` — copy local files to `dest/HotDict/` if not already present
- `sync_path_has_data(path)` — check if `path/HotDict/` already contains data
- `has_local_data()` — check if local default dir has data

**IMPORTANT**: In `app_delegate.applicationDidFinishLaunching_`, `Settings` must be initialised **before** `DataManager` so the sync path is available:
```python
self.settings     = Settings()
self.data_manager = DataManager(self.settings.sync_data_path)
```

### History eviction — LFU

`DataManager.HISTORY_CAP = 1000`. Each entry stores `{word, time, count}`.

- Re-looking up an existing word: removes it from current position, increments `count`, re-inserts at index 0 (most recent first).
- When cap exceeded: `_lfu_evict()` sorts by `count / (age_seconds + 1)` descending and keeps top 1000. Infrequent + stale entries are evicted first; high-frequency words are retained even if not recently accessed.

### Cache invalidation on URL change

Changing the lookup URL (in preferences or via `resetURL_`) automatically calls `data_manager.clear_cache()`. This ensures the next lookup re-fetches from the new URL rather than returning stale results from the previous language variant.

## Scraper Data Format

`scrape_cambridge(word, base_url="")` returns:

```python
{
  "word": str,
  "url": str,
  "pronunciations": [{"label": "uk"|"us", "ipa": str, "audio": str}],  # audio = full MP3 URL
  "entries": [
    {
      "pos": str,           # "noun", "verb", "phrase", etc. — DOM order preserved
      "pos_gram": str,      # "[ C or U ]" — entry-level grammar
      "source": str,        # dictionary source name, e.g. "Business English"
      "definitions": [
        {
          "en": str,        # English definition
          "zh": str,        # Chinese translation
          "gram": str,      # "[ T ]", "[ U ]" — per-definition grammar
          "label": str,     # "informal", "literary", etc.
          "usage": str,     # "not usually before noun"
          "guide": str,     # guideword, e.g. "POSITION"
          "examples": [{"en": str, "zh": str}],
          "synonyms": [{"word": str, "guide": str, "label": str}],
          "antonyms": [{"word": str, "guide": str, "label": str}],
          "phrases": [
            {
              "phrase": str,
              "gram": str,
              "cefr": str,
              "variant": str,
              "definitions": [...]   # same structure as parent definitions
            }
          ]
        }
      ]
    }
  ],
  "error": str              # present only on failure
}
```

### Pronunciation scraping — critical note

**Always iterate `.dpron-i` containers directly**, never `soup.select(".ipa")` globally.

Global `.ipa` scan causes two bugs:
1. Picks up IPA from unrelated page sections (e.g. sidebar widgets) when no `.dpron-i` ancestor exists.
2. When `.dpron-i` is not found, the ancestor walk exits at `body`, causing `.daud` search to span the entire document and grab wrong audio URLs.

Correct pattern:
```python
for dpron in soup.select(".dpron-i"):
    ipa_el = dpron.select_one(".ipa")
    region_el = dpron.find(class_=re.compile(r"\bdreg\b"))
    daud = dpron.find(class_="daud")
    ...
```

Phrase/idiom pages (e.g. "take care of") have zero `.dpron-i` elements → `pronunciations: []` is correct.

### Scraper DOM notes
- **DOM order**: POS entries are collected in page order by walking `.di-body` children directly; this preserves the source order including `phrase-di-block` entries.
- **phrase-di-block**: entries like `-rich` sit inside `.di-body` as siblings of `.entry`, not nested inside `.entry-body__el`. Detected via class `phrase-di-block` / `dphrase-di-block`.
- **Synonyms/antonyms**: scraped from `.xref.synonym`, `.xref.synonyms`, `.xref.opposite` blocks inside `ddef_block`. Each item's word text uses `get_text(separator=" ")` to preserve spaces (e.g. "the poor" not "thepoor").
- **Audio URL**: Cambridge `<source src>` uses relative paths — must prepend `https://dictionary.cambridge.org`.

## Settings / Hotkey

- Default lookup hotkey: `⌘⇧C` (keycode 8, modifiers `["cmd", "shift"]`)
- Default show-window hotkey: `⌘⌥Space` (keycode 49, modifiers `["cmd", "alt"]`)
- Modifier names: `"cmd"`, `"shift"`, `"alt"`, `"ctrl"`
- Change via right-click status bar icon → 偏好设置…
- Settings keys: `hotkey_keycode`, `hotkey_modifiers`, `show_window_keycode`, `show_window_modifiers`, `lookup_base_url`, `sidebar_open_on_start`, `font_size`, `sync_data_path`

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
│   ├── scroll_content    word display (fills full content_h), mask=2|16
│   └── overlay           centered error state, mask=2|16
├── sep_main              1px vertical divider, mask=1|16
└── left (sidebar)        历史/收藏, x=cw-LEFT_W, mask=1|16
    ├── search field      NSSearchField for real-time list filtering
    ├── tab buttons       历史 / 收藏
    └── table view        word list
```

- Sidebar defaults to **hidden** on startup; toggle via ☰ button in header right side.
- `settings.sidebar_open_on_start` is read on **first** `showWindow()` call only (`_first_shown` flag).
- **Sidebar search**: `NSSearchField` with `controlTextDidChange_` delegate for real-time filtering. Filter resets when switching tabs.
- **pron_bar removed** — UK/US audio buttons were removed. Pronunciation is now rendered inline inside the NSTextView (see Word Display below).

## Autocomplete — main_window.py

`_SuggestOverlay` is an `NSObject` that manages an in-window overlay `NSView` (not a separate `NSPanel`). It is attached to the main window's `contentView` so it works identically in dev and full py2app builds.

- **Data source**: `NSSpellChecker.completionsForPartialWordRange_inString_language_inSpellDocumentWithTag_` (system English dictionary, no bundled word list). History/favorites matches are prepended as personalised top results.
- **Trigger**: `controlTextDidChange_` on the main search field (requires `search_field.setDelegate_(self)` set in `_build()`). Fires when prefix ≥ 2 chars.
- **Positioning**: `search_field.convertRect_toView_(bounds, content_view)` → subtract overlay height → `NSMakeRect`. Re-orders overlay to front via `content_view.addSubview_positioned_relativeTo_(bg, 1, None)` each update.
- **Keyboard**: `control_textView_doCommandBySelector_` intercepts `moveDown:` / `moveUp:` (arrow navigation), `cancelOperation:` (Escape = dismiss), `insertNewline:` (Enter = apply selection and search).
- **Click**: `NSTableView` action `rowClicked_` — hides overlay then calls `_applySuggestion_` callback.
- **Auto-hide**: `windowDidResize_`, `windowDidMove_`, `windowDidResignKey_`, `searchEnter_`, `searchBtnClick_`.

### Why NSPanel was abandoned for the overlay

`NSPanel` with `NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel` is **invisible in py2app full builds** — `isVisible()` returns `True` but nothing renders. Root cause: borderless non-activating panels behave differently in the packaged app bundle context (different executable signature, different window server session). **Fix**: embed the dropdown as an `NSView` subview of the existing window's `contentView` instead.

## Word Display — word_display.py

### Background fill technique (critical)

**Reliable approach — use `█` fill chars**: append U+2588 FULL BLOCK characters with `fg = bg = fill_color`, followed by a bare `\n` (no background). The block chars have real glyph width, are not stripped by NSTextView, and are clipped at `tailIndent` by `NSLineBreakByClipping`. Since `fg = bg`, the partial clip at the right boundary is the same color as the bar — visually seamless.

```python
para.setTailIndent_(-50.0)
para.setLineBreakMode_(2)        # NSLineBreakByClipping
_append(mas, " text content ",  {... NSBackgroundColorAttributeName: color ...})
_append(mas, "█" * 300,         {NSFontAttributeName: same_font,
                                  NSForegroundColorAttributeName: color,   # fg = bg
                                  NSBackgroundColorAttributeName: color,
                                  NSParagraphStyleAttributeName: para})
_append(mas, "\n",              {... no NSBackgroundColorAttributeName ...})
```

**Do NOT rely on `\n`-in-background-run** to fill the line fragment: on macOS 15 (Mac Mini M4) this technique only fills to the last glyph bound — not to `tailIndent`. On macOS 14 it fills the full line fragment. The behavior is macOS-version-dependent and therefore unreliable.

**To limit background to text width only** (e.g. 同义词/反义词 header — intentionally short):
```python
_append(mas, " 同义词 ",  {... NSBackgroundColorAttributeName: c_xref_bg ...})
_append(mas, "\n",        {... no NSBackgroundColorAttributeName ...})
# \n NOT in background run → background stops at last glyph (works consistently)
```

### Bars in use

| Bar | Color | tailIndent | Fill approach |
|-----|-------|-----------|---------------|
| POS divider (`─`×44) | yellow fg, white bg | `-50` | foreground chars only, no bg |
| Source bar (word \| source) | yellow bg | `-50` | `\n` in bg run |
| Phrase banner (`▸ phrase`) | yellow bg | `-50` | `\n` in bg run |
| Xref header (同义词/反义词) | light blue bg | `_sep_width` (fixed) | `\n` separated, text-width only |

`_sep_width` is measured once: `NSAttributedString("─"×44, boldFont(15)).size().width` — used as the fixed tailIndent for xref headers so they align with the POS divider's natural character width.

### Other rendering details

- **Numbering**: skipped when a POS section has only one definition.
- **Deduplication**: `usage` field not shown as `▸ line` if already present in inline `gram`/`label` notes.
- **Example sentences**: italic via `NSFontManager.convertFont_toHaveTrait_(font, 1)` (NSItalicFontMask=1).
- **Synonyms/antonyms (xref)**: rendered after examples with light-blue header and clickable words. Each word is a `lookup://word` link handled by `textView_clickedOnLink_atIndex_`.
- **Phrase banner**: `▸ phrase  CEFR` on yellow background, same clip as source bar (`tailIndent=-50`).

### `lookup://` URL scheme

Clickable words in synonyms/antonyms use `NSLinkAttributeName: "lookup://word"`. Handled in `textView_clickedOnLink_atIndex_` in both `main_window.py` and `float_panel.py`:
- In main window: sets search field to word, triggers lookup
- In float panel: shows main window, triggers lookup there

### Pronunciation (inline in NSTextView)

- `🔊 label /ipa/` text is appended with `NSLinkAttributeName: audio_url`.
- **No blue underline**: `tv.setLinkTextAttributes_({NSForegroundColorAttributeName: NSColor.secondaryLabelColor()})`.
- **No URL tooltip**: `_WordTextView` overrides `addToolTipRect_owner_userData_` to return 0. (`setToolTip_` does NOT work for link tooltips — wrong level.)
- **Pointing hand cursor**: `_WordTextView` uses `NSTrackingMouseMoved=0x02 | NSTrackingActiveAlways=0x80` + `mouseMoved_` checking `NSLinkAttributeName` at pointer position.
- **Audio playback**: handled in `textView_clickedOnLink_atIndex_` in `main_window.py` and `float_panel.py`.

## Status Bar

- Icon: `"H"` (bold, size 14)
- Left-click: intercept in `menuWillOpen_`, cancel tracking, `setHighlighted_(True)`, show window, reset highlight after 0.15s via `performSelector_withObject_afterDelay_`.
- Right-click: standard NSMenu with 偏好设置 and 退出.

## Preferences Window — settings_window.py

Window size: `W=440, H=710`.

- Section 1: 划词查询快捷键 (record button)
- Section 2: 呼出主界面快捷键 (record button)
- Section 3: 查询接口地址 — URL field saves in three places: blur (`controlTextDidEndEditing_`), 保存 button (`saveSettings_`), and window close (`windowShouldClose_`). Changing URL also clears the cache. 恢复默认 saves immediately.
- Section 4: 侧边栏默认状态 — checkbox **auto-saves on toggle**.
- Section 5: 内容字体大小 — slider (10–22pt), continuous, **auto-applies via `applyFontSize` delegate**.
- Section 6: 数据同步路径 — folder picker (NSOpenPanel), readonly path display field, clear button. Auto-saves and applies immediately via `applySyncPath` delegate. If new dir is empty and local has data → migration alert.
- 保存/取消 buttons: 保存 also flushes URL field unconditionally (guards against focus never leaving the field). Only hotkey changes (Sections 1–2) strictly require 保存.

## 变更记录

### 2026-06-01
- 🆕 新增：主搜索框实时联想补全（`_SuggestOverlay`）——内嵌 NSView，调用 `NSSpellChecker` 系统英语词典，任意单词均可提示；历史/收藏匹配词优先置顶；↓↑/Enter/Esc 键盘导航；dev 和 full build 行为一致
- 🆕 新增：所有 `.py` 源文件顶部加版权声明（© 2026 EddieChan1993）
- 🐛 修复：音频缓存（`_playAudio_` + `_prefetchAudio` + `DataManager.audio_cache`）在 worktree 合并时被覆盖丢失，已恢复

### 2026-06-16
- ♻️ 优化：scraper 解析提速——`_fetch` 在解析前将 HTML 切到 `<article>` 标签（从 300-540KB 降到 85-290KB），解析耗时减少 60-90%；同时将后代选择器 `.pr.di.superentry .di-body` 简化为 `.di-body`（切片后无干扰节点），select 耗时减少 40%。典型查词时间：简单词 3s→1.9s，复杂词 6-7s→3.5-4s。

### 2026-06-14
- 🐛 修复：音频下载竞态——`DataManager.claim_audio_fetch` / `release_audio_fetch` 以 `threading.Event` 去重；用户点击时若 prefetch 正在下载同一 URL，则等待完成而非重复发起请求
- 🐛 修复：音频播放改回 afplay + `Popen`（非阻塞），撤销引起无声的 NSSound 方案（`NSSound.initWithData_` 在 py2app 打包环境下行为不可靠）
- 🐛 修复：`word_display.py` 发音行 IPA 末尾两个空格带 `NSLinkAttributeName`，导致两组发音之间空白区域误触发点击；改为单独 append 无链接属性的空格

### 2026-06-04
- 🆕 收藏列表改为按时间倒序排列（`get_favorites()` 按 `time` 字段降序排序，新收藏显示在最前）

### 2026-05-28
- 🐛 修复：音标抓取 bug——将 `soup.select(".ipa")` 全页扫描改为直接迭代 `.dpron-i` 容器，彻底解决短语词条（如"take care of"）错误显示无关词（horse/hoarse）音标 `/hɔːs/` `/hɔːrs/` 的问题
- ♻️ 回退：强制撤销破坏 Python 语法的 commit（dbd4b52 将 `\n`/`\\`/`\r` 转义符转为字面字符，导致 5 个文件语法错误），通过 `git reset --hard + force push` 恢复干净状态
- 🐛 修复：例句文本提取改用 `sep=""` 避免 `<b>` 包裹单词部分字符时（如 `mak<b>ing</b>`）插入空格导致 "mak ing" 断词显示
- 🐛 修复：新增 `_def_gram()` 辅助函数，排除位于 `.examp` 内的语法标签作为 definition 级别 gram；将例句内的 `.gram.dgram`（如 `[ + -ing verb ]`）正确提取并显示在对应例句行前
- 🐛 修复：新增 `_def_usage()` / `_def_variant()` — `.usage.dusage` 被误从 `.var.dvar` 内提取导致 "old use" 错误作为 usage note 显示；`_def_variant()` 提取 `.var.dvar` 完整文本（如 "( US also or old use die )"）新增 `variant` 字段并在 word_display 正确渲染

---

## Known Pitfalls

- **NSSplitView + window state restoration**: macOS overrides `setPosition_ofDividerAtIndex_` via saved state even with `setRestorable_(False)`. Solution: remove NSSplitView entirely and use plain NSView layout.
- **History for non-existent words**: only call `add_history` / `set_cached` when `has_entries` is True.
- **`NSMakeRect` import**: cannot import from Foundation — use tuples.
- **Status bar click highlight**: `menuWillOpen_` + `cancelTracking()` removes the system highlight; must manually call `setHighlighted_(True)` and schedule reset.
- **NSTextAlignmentCenter value differs by macOS version**: old AppKit used `NSCenterTextAlignment = 2`; newer macOS unified with UIKit so `NSTextAlignmentCenter = 1`, `NSTextAlignmentRight = 2`. **Never hardcode alignment integers** — always import and use the named constants.
- **Link tooltip suppression**: overriding `setToolTip_` on NSTextView subclass has no effect on link tooltips — NSTextView uses a private `NSToolTipWindow` mechanism. Override `addToolTipRect_owner_userData_` instead (return 0 to block all tooltip rects).
- **`\n`-in-background-run is macOS-version-dependent**: fills full line fragment on macOS 14, but only fills to glyph bounds on macOS 15 (Mac Mini M4). Use `█` fill chars (fg=bg=color) instead for cross-version reliability.
- **Settings before DataManager**: `Settings` must be initialised before `DataManager` in `applicationDidFinishLaunching_` so `sync_data_path` is available to the constructor.
- **`Path | None` type annotation**: requires Python 3.10+. Use `Optional[Path]` from `typing` for Python 3.9 compatibility — py2app will crash at import time otherwise.
- **`@objc.python_method` in plain Python classes**: only use on methods of `NSObject` subclasses. Applying it to a plain `class DataManager:` causes `NameError: name 'objc' is not defined` at import time.
- **Scraper fallback chain must not contain alternative language variants**: putting the simplified Chinese URL in `_FALLBACK_URLS` when the user configured traditional Chinese silently overrides their choice when Cambridge redirects. Fallback should only be the English-only URL as last resort.
- **URL field save only fires on blur (`controlTextDidEndEditing_`)**: if the user clicks 保存 without first clicking elsewhere, the text field never loses focus and the new URL is not saved. Fix: also flush the URL field value explicitly inside `saveSettings_` and `windowShouldClose_`.
- **Cache survives URL changes**: switching between language variants (simplified ↔ traditional) returns stale translated content from the old URL. Always call `data_manager.clear_cache()` when `lookup_base_url` changes.
- **NSPanel invisible in py2app full builds**: borderless non-activating `NSPanel` reports `isVisible() = True` but renders nothing after py2app packaging. Use an in-window `NSView` overlay instead (see `_SuggestOverlay` in `main_window.py`).
- **Never `cp` a worktree file over the main repo**: worktree branches are created from a snapshot of `main`; if other commits landed on `main` in the meantime, a blind `cp` silently discards them. Always work directly in the main repo (`/Users/eddiechan/code/cambridge/`) or use `git merge`/`cherry-pick` to integrate worktree changes.

## Global Hotkey — Lessons Learned (hard-won)

### Why CGEventTap / NSEvent monitor silently fail in py2app --dev builds

Both `CGEventTapCreate` and `NSEvent.addGlobalMonitorForEventsMatchingMask_handler_`
require macOS TCC permissions (Accessibility and Input Monitoring respectively).
**Each rebuild (dev or full) changes the executable's code signature**, which silently
invalidates the previously granted permission. Symptom: tap returns `None`, monitor
registers successfully but handler is never called — no error, no crash.

**Both permissions are mandatory** — Accessibility alone is not sufficient on newer macOS.
CGEventTap requires Accessibility; NSEvent global monitor (fallback) requires Input Monitoring.
Input Monitoring does **not** auto-prompt; user must enable it manually.

**Fix after any rebuild:**
```bash
tccutil reset Accessibility com.local.hotdict
tccutil reset ListenEvent com.local.hotdict
```
Then relaunch — it will re-prompt for Accessibility (grant it), then manually enable
Input Monitoring in System Settings → Privacy & Security → Input Monitoring.

**`build.sh` (full/non-dev mode) runs this reset automatically** after each build and
prints a reminder. Dev mode does not auto-reset (permissions usually survive dev rebuilds
in practice, since the binary changes less).

### HotkeyMonitor must be a plain Python class, not NSObject

Using `NSObject` as the base class caused PyObjC to silently swallow exceptions inside
`initWithDelegate_keycode_modifiers_`, preventing `_register` from ever running.
**Solution**: use a plain Python `class HotkeyMonitor:` with `__init__`.

### Defer hotkey registration until the run loop is running

`CGEventTapCreate` and `CFRunLoopAddSource` must be called after `NSApplication`
has started its run loop. Calling them in `applicationDidFinishLaunching_` is safe;
Carbon APIs (e.g. `GetApplicationEventTarget`) will segfault at that point — don't use them.

### GC will collect Python callbacks passed to C APIs

Always store callbacks as instance attributes to prevent GC:
```python
self._tap_cb  = _cb   # prevent GC of CGEventTap callback
self._tap_src = src   # prevent GC of CFRunLoopSource
self._ns_handler = _handler   # prevent GC of NSEvent monitor handler
```

### Carbon RegisterEventHotKey does NOT work in this AppKit + py2app context

`GetApplicationEventTarget()` segfaults — Carbon Event Manager is not initialised in a
pure AppKit run loop. Stick with CGEventTap + NSEvent global monitor fallback.

### File I/O: always specify encoding="utf-8"

`open()` without encoding defaults to ASCII on some locales, causing `UnicodeEncodeError`
inside callbacks which silently swallows the error and returns the event unmodified.

### Hotkey lookup order: get selected text BEFORE stealing focus

`hotkeyTriggered` must call `_getSelectedText()` **before** `showWindow()`.
`showWindow()` activates HotDict, so any simulated `Cmd+C` sent afterwards goes to
HotDict itself, not the source app.

### Run _getSelectedText on a background thread

`_getSelectedText` calls `time.sleep(0.15)`. On the main thread this blocks the
CGEventTap callback loop → macOS beeps and may disable the tap.
Run in `threading.Thread`, dispatch result back via `run_on_main_thread`.

### Debugging stdout is invisible in py2app builds

Use file logging: `open("/tmp/hotdict_init.log", "a", encoding="utf-8")`.

## Dependencies

```
pyobjc-core / pyobjc-framework-Cocoa / pyobjc-framework-Quartz
requests, beautifulsoup4, lxml   — scraping
openpyxl                         — favorites XLSX export
py2app                           — packaging
```

Python 3.9+ required. Anaconda Python is explicitly excluded by `build.sh` due to PyObjC incompatibilities.
