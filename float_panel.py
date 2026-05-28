# Copyright © 2026 EddieChan1993. All rights reserved.
# Unauthorized commercial use is strictly prohibited.
"""
Floating lookup panel (NSPanel) that appears on the left side of the screen.

• ESC or ✕ closes it.
• Clicking outside does NOT close it.
• Shows word info + favourite toggle button.
"""

import objc
from Foundation import NSObject, NSMakeRect, NSMakeSize
from AppKit import (
    NSPanel,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskNonactivatingPanel,
    NSWindowStyleMaskUtilityWindow,
    NSBackingStoreBuffered,
    NSScreen,
    NSView,
    NSButton,
    NSTextField,
    NSScrollView,
    NSColor,
    NSFont,
    NSBezelStyleRounded,
    NSButtonTypeMomentaryLight,
    NSButtonTypeToggle,
    NSOnState,
    NSOffState,
    NSMakeRect,
    NSVisualEffectView,
    NSVisualEffectBlendingModeBehindWindow,
    NSVisualEffectMaterialSidebar,
)

from word_display import make_word_scroll_view, update_word_view


# ── Hover-aware favourite button ─────────────────────────────────────────────

class FavButton(NSButton):
    """Star button with hover colour change and animated label swap."""

    def initWithFrame_(self, frame):
        self = objc.super(FavButton, self).initWithFrame_(frame)
        if self is None:
            return None
        self._hovered = False
        self._isFav = False
        self.setBezelStyle_(NSBezelStyleRounded)
        self.setButtonType_(NSButtonTypeToggle)
        self.setFont_(NSFont.systemFontOfSize_(18))
        self.setTitle_("☆")
        self.setBordered_(False)
        opts = 0x01 | 0x80  # NSTrackingMouseEnteredAndExited | NSTrackingActiveAlways
        from AppKit import NSTrackingArea
        ta = NSTrackingArea.alloc().initWithRect_options_owner_userInfo_(
            self.bounds(), opts, self, None
        )
        self.addTrackingArea_(ta)
        return self

    def setFavorite_(self, flag: bool):
        self._isFav = flag
        self.setTitle_("★" if flag else "☆")
        color = NSColor.systemYellowColor() if flag else NSColor.secondaryLabelColor()
        self.setContentTintColor_(color)

    def mouseEntered_(self, event):
        self._hovered = True
        self.setNeedsDisplay_(True)

    def mouseExited_(self, event):
        self._hovered = False
        self.setNeedsDisplay_(True)

    def drawRect_(self, rect):
        if self._hovered:
            NSColor.colorWithWhite_alpha_(0.5, 0.15).setFill()
            from AppKit import NSBezierPath
            path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                self.bounds(), 6, 6
            )
            path.fill()
        objc.super(FavButton, self).drawRect_(rect)


# ── Floating panel ────────────────────────────────────────────────────────────

PANEL_W = 400
PANEL_H = 580


class FloatPanel(NSObject):
    def init(self):
        self = objc.super(FloatPanel, self).init()
        if self is None:
            return None
        self._panel = None
        self._tv = None
        self._fav_btn = None
        self._word_label = None
        self._current_data = None
        self._delegate = None   # set by AppDelegate
        self._build()
        return self

    # ── Build ─────────────────────────────────────────────────────────────────

    @objc.python_method
    def _build(self):
        style = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskNonactivatingPanel
            | NSWindowStyleMaskUtilityWindow
        )
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, PANEL_W, PANEL_H),
            style,
            NSBackingStoreBuffered,
            False,
        )
        panel.setTitle_("HotDict")
        panel.setFloatingPanel_(True)
        panel.setHidesOnDeactivate_(False)
        panel.setBecomesKeyOnlyIfNeeded_(True)
        panel.setReleasedWhenClosed_(False)
        panel.setBackgroundColor_(NSColor.windowBackgroundColor())
        panel.setDelegate_(self)

        content = panel.contentView()
        cw = PANEL_W
        ch = PANEL_H

        # Toolbar row: word label + fav button
        toolbar_h = 36
        word_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(12, ch - toolbar_h, cw - 60, toolbar_h)
        )
        word_label.setBezeled_(False)
        word_label.setDrawsBackground_(False)
        word_label.setEditable_(False)
        word_label.setSelectable_(True)
        word_label.setFont_(NSFont.boldSystemFontOfSize_(15))
        word_label.setStringValue_("")
        word_label.setAutoresizingMask_(2)  # width sizable
        content.addSubview_(word_label)

        fav_btn = FavButton.alloc().initWithFrame_(
            NSMakeRect(cw - 48, ch - toolbar_h, 44, 36)
        )
        fav_btn.setTarget_(self)
        fav_btn.setAction_("toggleFavorite:")
        fav_btn.setAutoresizingMask_(4 | 64)  # right + top margin
        content.addSubview_(fav_btn)

        # Divider
        div = NSView.alloc().initWithFrame_(NSMakeRect(0, ch - toolbar_h - 1, cw, 1))
        div.setWantsLayer_(True)
        div.layer().setBackgroundColor_(
            NSColor.separatorColor().CGColor()
        )
        div.setAutoresizingMask_(2 | 64)
        content.addSubview_(div)

        # Scroll view for word content
        scroll_h = ch - toolbar_h - 2
        scroll, tv = make_word_scroll_view(NSMakeRect(0, 0, cw, scroll_h))
        scroll.setAutoresizingMask_(2 | 16)
        tv.setDelegate_(self)
        content.addSubview_(scroll)

        self._panel = panel
        self._tv = tv
        self._fav_btn = fav_btn
        self._word_label = word_label

        # Position left side of screen
        self._positionPanel()

    @objc.python_method
    def _positionPanel(self):
        screen = NSScreen.mainScreen()
        if not screen:
            return
        sf = screen.visibleFrame()
        x = sf.origin.x + 20
        y = sf.origin.y + (sf.size.height - PANEL_H) / 2
        self._panel.setFrameOrigin_((x, y))

    # ── Public API ────────────────────────────────────────────────────────────

    def showWithWord_loading_(self, word: str, loading: bool):
        self._word_label.setStringValue_(word)
        self._fav_btn.setFavorite_(False)
        if loading:
            from word_display import build_attributed_string
            update_word_view(self._tv, {"word": word, "entries": [], "pronunciations": [],
                                        "_loading": True})
            # Show "loading…" placeholder text
            from Foundation import NSAttributedString
            from AppKit import NSFontAttributeName, NSForegroundColorAttributeName
            ph = NSAttributedString.alloc().initWithString_attributes_(
                "查询中…",
                {
                    NSFontAttributeName: NSFont.systemFontOfSize_(15),
                    NSForegroundColorAttributeName: NSColor.tertiaryLabelColor(),
                },
            )
            self._tv.textStorage().setAttributedString_(ph)

        self._panel.orderFrontRegardless()

    def updateWithResult_(self, data: dict):
        self._current_data = data
        word = data.get("word", "")
        self._word_label.setStringValue_(word)
        update_word_view(self._tv, data)
        self._prefetchAudio(data)   # pre-download audio so clicks are instant

        if self._delegate and hasattr(self._delegate, "data_manager"):
            is_fav = self._delegate.data_manager.is_favorite(word)
            self._fav_btn.setFavorite_(is_fav)

    @objc.python_method
    def hide(self):
        self._panel.orderOut_(None)

    # ── NSTextViewDelegate — pronunciation link clicks ─────────────────────────

    def textView_clickedOnLink_atIndex_(self, tv, link, char_index):
        url = str(link)
        if url.startswith("http"):
            self._playAudio_(url)
            return True
        if url.startswith("lookup://"):
            word = url[len("lookup://"):]
            if word and self._delegate:
                self._delegate.main_window.showWindow()
                self._delegate.lookupWordInMainWindow_(word)
            return True
        return False

    @objc.python_method
    def _playAudio_(self, url: str):
        """Play audio — uses DataManager.audio_cache shared with main window."""
        if not url:
            return
        from main_window import MainWindowController
        dm = self._delegate.data_manager if self._delegate else None
        import threading, subprocess, tempfile, os, requests as _req
        ac = dm.audio_cache if dm else {}

        def _play(data: bytes):
            try:
                with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                    f.write(data)
                    tmp = f.name
                subprocess.run(["afplay", tmp], check=False)
                os.unlink(tmp)
            except Exception as e:
                print(f"[Audio] play error: {e}")

        def _run():
            try:
                if url in ac:
                    _play(ac[url])
                    return
                r = _req.get(url, headers=MainWindowController._AUDIO_HEADERS, timeout=10)
                r.raise_for_status()
                if dm:
                    dm.put_audio_cache(url, r.content)
                _play(ac[url])
            except Exception as e:
                print(f"[Audio] {e}")

        threading.Thread(target=_run, daemon=True).start()

    @objc.python_method
    def _prefetchAudio(self, data: dict):
        """Pre-download pronunciation audio into DataManager.audio_cache."""
        from main_window import MainWindowController
        dm = self._delegate.data_manager if self._delegate else None
        if not dm:
            return
        import threading, requests as _req
        ac = dm.audio_cache
        urls = [
            p.get("audio", "")
            for p in (data or {}).get("pronunciations", [])
            if p.get("audio") and p["audio"] not in ac
        ]
        if not urls:
            return

        def _fetch(url):
            try:
                r = _req.get(url, headers=MainWindowController._AUDIO_HEADERS, timeout=10)
                if r.ok:
                    dm.put_audio_cache(url, r.content)
            except Exception:
                pass

        for url in urls:
            threading.Thread(target=_fetch, args=(url,), daemon=True).start()

    # ── Actions ───────────────────────────────────────────────────────────────

    @objc.IBAction
    def toggleFavorite_(self, sender):
        if not self._current_data:
            return
        word = self._current_data.get("word", "")
        if not word or not self._delegate:
            return
        dm = self._delegate.data_manager
        is_fav = dm.toggle_favorite(word, self._current_data)
        self._fav_btn.setFavorite_(is_fav)
        if hasattr(self._delegate, "refreshFavorites"):
            self._delegate.refreshFavorites()

    # ── NSWindowDelegate ──────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._panel.orderOut_(None)
        return False

    def windowDidResize_(self, notification):
        # Reflow text container width
        w = self._panel.contentView().frame().size.width
        self._tv.textContainer().setContainerSize_((w, 1e7))
