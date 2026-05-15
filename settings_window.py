"""Hotkey settings window."""

import objc
from Foundation import NSObject, NSMakeRect
from AppKit import (
    NSWindow,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskClosable,
    NSBackingStoreBuffered,
    NSTextField,
    NSButton,
    NSSlider,
    NSColor,
    NSFont,
    NSBezelStyleRounded,
    NSButtonTypeMomentaryLight,
    NSScreen,
    NSApplication,
    NSEventMaskKeyDown,
    NSEvent,
    NSNormalWindowLevel,
    NSTextAlignmentCenter,
    NSTextAlignmentRight,
)

from settings import Settings, hotkey_display, check_conflict

W, H = 440, 560
M = 24          # left/right margin
IW = W - 2 * M  # inner width = 392


class SettingsWindowController(NSObject):

    def initWithSettings_delegate_(self, settings, delegate):
        self = objc.super(SettingsWindowController, self).init()
        if self is None:
            return None
        self._settings          = settings
        self._delegate          = delegate
        self._pending_keycode   = settings.hotkey_keycode
        self._pending_modifiers = list(settings.hotkey_modifiers)
        self._recording         = False
        self._monitor           = None
        self._pending_show_keycode   = settings.show_window_keycode
        self._pending_show_modifiers = list(settings.show_window_modifiers)
        self._recording_show    = False
        self._show_monitor      = None
        self._window            = None
        self._hotkey_field      = None
        self._conflict_label    = None
        self._record_btn        = None
        self._show_field        = None
        self._show_conflict     = None
        self._show_record_btn   = None
        self._url_field         = None
        self._sidebar_check     = None
        self._font_slider       = None
        self._font_size_label   = None
        self._build()
        return self

    # ── Build ─────────────────────────────────────────────────────────────────

    @objc.python_method
    def _build(self):
        screen = NSScreen.mainScreen()
        sf = screen.visibleFrame() if screen else NSMakeRect(0, 0, 1280, 800)
        wx = sf.origin.x + (sf.size.width  - W) / 2
        wy = sf.origin.y + (sf.size.height - H) / 2

        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(wx, wy, W, H), style, NSBackingStoreBuffered, False)
        win.setTitle_("偏好设置")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        win.setLevel_(NSNormalWindowLevel + 2)

        c = win.contentView()

        # Helpers — all coordinates expressed as (top_from_top, height).
        # NSMakeRect uses bottom-left origin, so y = H - top - h.

        def R(x, top, w, h):
            return NSMakeRect(x, H - top - h, w, h)

        def RI(top, h):  # full-width inset rect
            return R(M, top, IW, h)

        def _lbl(text, top, h, bold=False, size=13, color=None, align=None):
            f = NSTextField.alloc().initWithFrame_(RI(top, h))
            f.setStringValue_(text)
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False); f.setSelectable_(False)
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold
                       else NSFont.systemFontOfSize_(size))
            if color:
                f.setTextColor_(color)
            if align is not None:
                f.setAlignment_(align)
            return f

        def _sep(top):
            s = NSTextField.alloc().initWithFrame_(NSMakeRect(0, H - top - 1, W, 1))
            s.setBezeled_(False); s.setDrawsBackground_(True)
            s.setEditable_(False); s.setSelectable_(False)
            s.setBackgroundColor_(NSColor.separatorColor())
            return s

        def _hotkey_field(top, value):
            FIELD_W = IW - 8 - 92
            f = NSTextField.alloc().initWithFrame_(R(M, top, FIELD_W, 30))
            f.setStringValue_(value)
            f.setBezeled_(True); f.setBezelStyle_(1)
            f.setEditable_(False); f.setSelectable_(False)
            f.setAlignment_(NSTextAlignmentCenter)
            f.setFont_(NSFont.monospacedSystemFontOfSize_weight_(16, 0.0))
            return f

        def _record_btn(top, action):
            btn = NSButton.alloc().initWithFrame_(R(M + IW - 92, top, 92, 30))
            btn.setTitle_("重新录制")
            btn.setBezelStyle_(NSBezelStyleRounded)
            btn.setButtonType_(NSButtonTypeMomentaryLight)
            btn.setFont_(NSFont.systemFontOfSize_(12))
            btn.setTarget_(self); btn.setAction_(action)
            return btn

        def _conflict(top):
            f = NSTextField.alloc().initWithFrame_(RI(top, 13))
            f.setStringValue_("")
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False)
            f.setFont_(NSFont.systemFontOfSize_(11))
            f.setTextColor_(NSColor.systemOrangeColor())
            return f

        GRAY = NSColor.secondaryLabelColor()

        # ── Section 1: 全局查词快捷键 ─────────────────────────────────────────
        # top=20  title
        # top=42  subtitle  (gap 4)
        # top=62  hotkey row  (gap 7 after subtitle h=13 → 42+13+7=62)
        # top=96  conflict  (gap 4)
        # top=115 separator  (gap 6)
        c.addSubview_(_lbl("全局查词快捷键", 20, 18, bold=True))
        c.addSubview_(_lbl("设置划词查询的全局快捷键。录制时按 ESC 取消。",
                           42, 13, size=11, color=GRAY))
        hotkey_field = _hotkey_field(62, self._settings.hotkey_display_string())
        c.addSubview_(hotkey_field)
        record_btn = _record_btn(62, "startRecording:")
        c.addSubview_(record_btn)
        conflict_label = _conflict(96)
        c.addSubview_(conflict_label)
        c.addSubview_(_sep(115))

        # ── Section 2: 呼出主界面快捷键 ──────────────────────────────────────
        # top=135 title  (gap 20)
        # top=157 subtitle
        # top=177 hotkey row
        # top=211 conflict
        # top=230 separator
        c.addSubview_(_lbl("呼出主界面快捷键", 135, 18, bold=True))
        c.addSubview_(_lbl("直接呼出/隐藏主窗口，无需选中文字。",
                           157, 13, size=11, color=GRAY))
        show_field = _hotkey_field(177, self._settings.show_window_display_string())
        c.addSubview_(show_field)
        show_record_btn = _record_btn(177, "startRecordingShow:")
        c.addSubview_(show_record_btn)
        show_conflict = _conflict(211)
        c.addSubview_(show_conflict)
        c.addSubview_(_sep(230))

        # ── Section 3: 查询接口地址 ───────────────────────────────────────────
        # top=250 title
        # top=272 subtitle
        # top=292 url field
        # top=326 reset button
        # top=356 separator
        c.addSubview_(_lbl("查询接口地址", 250, 18, bold=True))
        c.addSubview_(_lbl("修改后将在下次查词时生效，留空则恢复默认。",
                           272, 13, size=11, color=GRAY))

        url_field = NSTextField.alloc().initWithFrame_(RI(292, 26))
        url_field.setStringValue_(self._settings.lookup_base_url)
        url_field.setBezeled_(True); url_field.setBezelStyle_(1)
        url_field.setEditable_(True)
        url_field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        url_field.setPlaceholderString_("https://dictionary.cambridge.org/...")
        url_field.setDelegate_(self)
        c.addSubview_(url_field)

        reset_btn = NSButton.alloc().initWithFrame_(R(M, 326, 80, 22))
        reset_btn.setTitle_("恢复默认")
        reset_btn.setBezelStyle_(NSBezelStyleRounded)
        reset_btn.setButtonType_(NSButtonTypeMomentaryLight)
        reset_btn.setFont_(NSFont.systemFontOfSize_(11))
        reset_btn.setTarget_(self); reset_btn.setAction_("resetURL:")
        c.addSubview_(reset_btn)
        c.addSubview_(_sep(356))

        # ── Section 4: 侧边栏默认状态 ─────────────────────────────────────────
        # top=376 title
        # top=402 checkbox
        # top=432 separator
        c.addSubview_(_lbl("侧边栏默认状态", 376, 18, bold=True))

        sidebar_check = NSButton.alloc().initWithFrame_(RI(402, 22))
        sidebar_check.setButtonType_(3)  # NSButtonTypeSwitch
        sidebar_check.setTitle_("启动时默认展开历史/收藏侧边栏")
        sidebar_check.setFont_(NSFont.systemFontOfSize_(13))
        sidebar_check.setState_(1 if self._settings.sidebar_open_on_start else 0)
        sidebar_check.setTarget_(self); sidebar_check.setAction_("toggleSidebarDefault:")
        c.addSubview_(sidebar_check)
        c.addSubview_(_sep(432))

        # ── Section 5: 内容字体大小 ───────────────────────────────────────────
        # top=452 title
        # top=474 subtitle
        # top=494 slider row (h=22)
        c.addSubview_(_lbl("内容字体大小", 452, 18, bold=True))
        c.addSubview_(_lbl("拖动滑块调整，实时预览效果。",
                           474, 13, size=11, color=GRAY))

        cur_size = self._settings.font_size

        # Slider row layout: A [====slider====] A  16 pt
        SROW_TOP = 494
        SA_W, SA_H = 14, 14   # small "A"
        BA_W, BA_H = 18, 18   # big "A"
        PT_W, PT_H = 44, 14   # "16 pt" label
        SLD_H = 20
        GAP = 6

        c.addSubview_(_lbl("A", SROW_TOP + 4, SA_H, size=10, color=GRAY))

        pt_x = M + IW - PT_W
        font_size_label = NSTextField.alloc().initWithFrame_(
            R(pt_x, SROW_TOP + 4, PT_W, PT_H))
        font_size_label.setStringValue_(f"{cur_size} pt")
        font_size_label.setBezeled_(False); font_size_label.setDrawsBackground_(False)
        font_size_label.setEditable_(False); font_size_label.setSelectable_(False)
        font_size_label.setAlignment_(NSTextAlignmentRight)
        font_size_label.setFont_(NSFont.monospacedSystemFontOfSize_weight_(12, 0.0))
        font_size_label.setTextColor_(GRAY)
        c.addSubview_(font_size_label)

        big_a_x = pt_x - GAP - BA_W
        big_a = NSTextField.alloc().initWithFrame_(
            R(big_a_x, SROW_TOP + 2, BA_W, BA_H))
        big_a.setStringValue_("A")
        big_a.setBezeled_(False); big_a.setDrawsBackground_(False)
        big_a.setEditable_(False); big_a.setSelectable_(False)
        big_a.setFont_(NSFont.boldSystemFontOfSize_(16))
        big_a.setTextColor_(GRAY)
        c.addSubview_(big_a)

        sld_x = M + SA_W + GAP
        sld_w = big_a_x - GAP - sld_x
        font_slider = NSSlider.alloc().initWithFrame_(
            R(sld_x, SROW_TOP + 1, sld_w, SLD_H))
        font_slider.setMinValue_(10)
        font_slider.setMaxValue_(22)
        font_slider.setIntValue_(cur_size)
        font_slider.setNumberOfTickMarks_(13)
        font_slider.setAllowsTickMarkValuesOnly_(True)
        font_slider.setContinuous_(True)
        font_slider.setTarget_(self); font_slider.setAction_("fontSizeChanged:")
        c.addSubview_(font_slider)

        # ── Bottom buttons ─────────────────────────────────────────────────────
        BTN_W_B, BTN_H_B, BTN_Y = 80, 28, 16
        save_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(W - M - BTN_W_B, BTN_Y, BTN_W_B, BTN_H_B))
        save_btn.setTitle_("保存")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setButtonType_(NSButtonTypeMomentaryLight)
        save_btn.setFont_(NSFont.systemFontOfSize_(13))
        save_btn.setTarget_(self); save_btn.setAction_("saveSettings:")
        save_btn.setKeyEquivalent_("\r")
        c.addSubview_(save_btn)

        cancel_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(W - M - BTN_W_B - 8 - BTN_W_B, BTN_Y, BTN_W_B, BTN_H_B))
        cancel_btn.setTitle_("取消")
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setButtonType_(NSButtonTypeMomentaryLight)
        cancel_btn.setFont_(NSFont.systemFontOfSize_(13))
        cancel_btn.setTarget_(self); cancel_btn.setAction_("cancelSettings:")
        c.addSubview_(cancel_btn)

        self._window          = win
        self._hotkey_field    = hotkey_field
        self._conflict_label  = conflict_label
        self._record_btn      = record_btn
        self._show_field      = show_field
        self._show_conflict   = show_conflict
        self._show_record_btn = show_record_btn
        self._url_field       = url_field
        self._sidebar_check   = sidebar_check
        self._font_slider     = font_slider
        self._font_size_label = font_size_label

    # ── Helpers ───────────────────────────────────────────────────────────────

    @objc.python_method
    def _refresh_display(self):
        self._hotkey_field.setStringValue_(
            hotkey_display(self._pending_keycode, self._pending_modifiers))
        conflict = check_conflict(self._pending_keycode, self._pending_modifiers)
        self._conflict_label.setStringValue_(
            f"⚠️ 可能与系统快捷键冲突：{conflict}" if conflict else "")

    @objc.python_method
    def _refresh_show_display(self):
        self._show_field.setStringValue_(
            hotkey_display(self._pending_show_keycode, self._pending_show_modifiers))
        conflict = check_conflict(self._pending_show_keycode, self._pending_show_modifiers)
        self._show_conflict.setStringValue_(
            f"⚠️ 可能与系统快捷键冲突：{conflict}" if conflict else "")

    @objc.python_method
    def _stop_recording(self):
        self._recording = False
        if self._monitor:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None
        self._record_btn.setTitle_("重新录制")
        self._record_btn.setEnabled_(True)

    @objc.python_method
    def _stop_recording_show(self):
        self._recording_show = False
        if self._show_monitor:
            NSEvent.removeMonitor_(self._show_monitor)
            self._show_monitor = None
        self._show_record_btn.setTitle_("重新录制")
        self._show_record_btn.setEnabled_(True)

    # ── Actions ───────────────────────────────────────────────────────────────

    @objc.IBAction
    def startRecording_(self, sender):
        if self._recording:
            return
        self._recording = True
        self._record_btn.setTitle_("按下快捷键…")
        self._record_btn.setEnabled_(False)
        self._hotkey_field.setStringValue_("请按下快捷键…")
        self._conflict_label.setStringValue_("")

        ctrl = self

        def _handler(event):
            if not ctrl._recording:
                return event
            keycode = event.keyCode()
            flags   = event.modifierFlags()

            if keycode == 53:       # ESC — cancel recording
                ctrl._stop_recording()
                ctrl._refresh_display()
                return None

            mods = []
            if flags & 0x40000:  mods.append("ctrl")
            if flags & 0x80000:  mods.append("alt")
            if flags & 0x20000:  mods.append("shift")
            if flags & 0x100000: mods.append("cmd")

            if not mods:            # bare key — ignore, keep recording
                return event

            ctrl._pending_keycode   = keycode
            ctrl._pending_modifiers = mods
            ctrl._stop_recording()
            ctrl._refresh_display()
            return None             # consume event

        self._monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, _handler)

    @objc.IBAction
    def startRecordingShow_(self, sender):
        if self._recording_show:
            return
        self._recording_show = True
        self._show_record_btn.setTitle_("按下快捷键…")
        self._show_record_btn.setEnabled_(False)
        self._show_field.setStringValue_("请按下快捷键…")
        self._show_conflict.setStringValue_("")

        ctrl = self

        def _handler(event):
            if not ctrl._recording_show:
                return event
            keycode = event.keyCode()
            flags   = event.modifierFlags()

            if keycode == 53:
                ctrl._stop_recording_show()
                ctrl._refresh_show_display()
                return None

            mods = []
            if flags & 0x40000:  mods.append("ctrl")
            if flags & 0x80000:  mods.append("alt")
            if flags & 0x20000:  mods.append("shift")
            if flags & 0x100000: mods.append("cmd")

            if not mods:
                return event

            ctrl._pending_show_keycode   = keycode
            ctrl._pending_show_modifiers = mods
            ctrl._stop_recording_show()
            ctrl._refresh_show_display()
            return None

        self._show_monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, _handler)

    @objc.IBAction
    def cancelSettings_(self, sender):
        self._stop_recording()
        self._stop_recording_show()
        self._window.orderOut_(None)

    @objc.IBAction
    def resetURL_(self, sender):
        from settings import DEFAULT_LOOKUP_URL
        self._url_field.setStringValue_(DEFAULT_LOOKUP_URL)
        self._settings.set_lookup_base_url(DEFAULT_LOOKUP_URL)

    @objc.IBAction
    def toggleSidebarDefault_(self, sender):
        self._settings.set_sidebar_open_on_start(sender.state() == 1)

    @objc.IBAction
    def fontSizeChanged_(self, sender):
        size = int(sender.intValue())
        self._font_size_label.setStringValue_(f"{size} pt")
        if self._delegate and hasattr(self._delegate, "applyFontSize"):
            self._delegate.applyFontSize(size)

    def controlTextDidEndEditing_(self, notification):
        if notification.object() != self._url_field:
            return
        url = self._url_field.stringValue().strip()
        from settings import DEFAULT_LOOKUP_URL
        self._settings.set_lookup_base_url(url if url else DEFAULT_LOOKUP_URL)

    @objc.IBAction
    def saveSettings_(self, sender):
        self._stop_recording()
        self._stop_recording_show()
        self._settings.set_hotkey(self._pending_keycode, self._pending_modifiers)
        if self._delegate and hasattr(self._delegate, "applyNewHotkey"):
            self._delegate.applyNewHotkey(
                self._pending_keycode, self._pending_modifiers)
        self._settings.set_show_window_hotkey(
            self._pending_show_keycode, self._pending_show_modifiers)
        if self._delegate and hasattr(self._delegate, "applyNewShowWindowHotkey"):
            self._delegate.applyNewShowWindowHotkey(
                self._pending_show_keycode, self._pending_show_modifiers)
        self._window.orderOut_(None)

    # ── NSWindowDelegate ──────────────────────────────────────────────────────

    def windowShouldClose_(self, sender):
        self._stop_recording()
        self._stop_recording_show()
        return True

    # ── Public ────────────────────────────────────────────────────────────────

    @objc.python_method
    def showWindow(self):
        self._pending_keycode        = self._settings.hotkey_keycode
        self._pending_modifiers      = list(self._settings.hotkey_modifiers)
        self._pending_show_keycode   = self._settings.show_window_keycode
        self._pending_show_modifiers = list(self._settings.show_window_modifiers)
        self._refresh_display()
        self._refresh_show_display()
        self._url_field.setStringValue_(self._settings.lookup_base_url)
        self._sidebar_check.setState_(
            1 if self._settings.sidebar_open_on_start else 0)
        cur = self._settings.font_size
        self._font_slider.setIntValue_(cur)
        self._font_size_label.setStringValue_(f"{cur} pt")
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.orderFrontRegardless()
