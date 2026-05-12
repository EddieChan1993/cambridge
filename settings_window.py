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
)

from settings import Settings, hotkey_display, check_conflict

W, H = 400, 290


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
        self._build()
        return self

    # ── Build ─────────────────────────────────────────────────────────────────

    @objc.python_method
    def _build(self):
        screen = NSScreen.mainScreen()
        sf = screen.visibleFrame() if screen else NSMakeRect(0, 0, 1280, 800)
        x = sf.origin.x + (sf.size.width  - W) / 2
        y = sf.origin.y + (sf.size.height - H) / 2

        style = NSWindowStyleMaskTitled | NSWindowStyleMaskClosable
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, W, H), style, NSBackingStoreBuffered, False)
        win.setTitle_("偏好设置")
        win.setReleasedWhenClosed_(False)
        win.setDelegate_(self)
        win.setLevel_(NSNormalWindowLevel + 2)

        c = win.contentView()

        def _static(text, x, y, w, h, bold=False, size=13, color=None):
            f = NSTextField.alloc().initWithFrame_(NSMakeRect(x, y, w, h))
            f.setStringValue_(text)
            f.setBezeled_(False); f.setDrawsBackground_(False)
            f.setEditable_(False); f.setSelectable_(False)
            f.setFont_(NSFont.boldSystemFontOfSize_(size) if bold
                       else NSFont.systemFontOfSize_(size))
            if color:
                f.setTextColor_(color)
            return f

        # ── Section 1: 划词查询快捷键 ────────────────────────────────────────
        c.addSubview_(_static("全局查词快捷键", 20, H-38, 200, 18, bold=True))
        c.addSubview_(_static("设置划词查询的全局快捷键。录制时按 ESC 取消。",
                              20, H-58, W-40, 16, size=11,
                              color=NSColor.secondaryLabelColor()))

        hotkey_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, H-96, 162, 30))
        hotkey_field.setStringValue_(self._settings.hotkey_display_string())
        hotkey_field.setBezeled_(True)
        hotkey_field.setBezelStyle_(1)
        hotkey_field.setEditable_(False)
        hotkey_field.setSelectable_(False)
        hotkey_field.setAlignment_(NSTextAlignmentCenter)
        hotkey_field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(16, 0.0))
        c.addSubview_(hotkey_field)

        record_btn = NSButton.alloc().initWithFrame_(NSMakeRect(194, H-96, 90, 30))
        record_btn.setTitle_("重新录制")
        record_btn.setBezelStyle_(NSBezelStyleRounded)
        record_btn.setButtonType_(NSButtonTypeMomentaryLight)
        record_btn.setFont_(NSFont.systemFontOfSize_(12))
        record_btn.setTarget_(self)
        record_btn.setAction_("startRecording:")
        c.addSubview_(record_btn)

        conflict_label = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, H-118, W-40, 16))
        conflict_label.setStringValue_("")
        conflict_label.setBezeled_(False); conflict_label.setDrawsBackground_(False)
        conflict_label.setEditable_(False)
        conflict_label.setFont_(NSFont.systemFontOfSize_(11))
        conflict_label.setTextColor_(NSColor.systemOrangeColor())
        c.addSubview_(conflict_label)

        # ── Separator ────────────────────────────────────────────────────────
        sep = NSTextField.alloc().initWithFrame_(NSMakeRect(20, H-130, W-40, 1))
        sep.setBezeled_(False); sep.setDrawsBackground_(True)
        sep.setEditable_(False); sep.setSelectable_(False)
        sep.setBackgroundColor_(NSColor.separatorColor())
        c.addSubview_(sep)

        # ── Section 2: 呼出主界面快捷键 ──────────────────────────────────────
        c.addSubview_(_static("呼出主界面快捷键", 20, H-152, 200, 18, bold=True))
        c.addSubview_(_static("直接呼出/隐藏主窗口，无需选中文字。",
                              20, H-172, W-40, 16, size=11,
                              color=NSColor.secondaryLabelColor()))

        show_field = NSTextField.alloc().initWithFrame_(NSMakeRect(20, H-210, 162, 30))
        show_field.setStringValue_(self._settings.show_window_display_string())
        show_field.setBezeled_(True)
        show_field.setBezelStyle_(1)
        show_field.setEditable_(False)
        show_field.setSelectable_(False)
        show_field.setAlignment_(NSTextAlignmentCenter)
        show_field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(16, 0.0))
        c.addSubview_(show_field)

        show_record_btn = NSButton.alloc().initWithFrame_(NSMakeRect(194, H-210, 90, 30))
        show_record_btn.setTitle_("重新录制")
        show_record_btn.setBezelStyle_(NSBezelStyleRounded)
        show_record_btn.setButtonType_(NSButtonTypeMomentaryLight)
        show_record_btn.setFont_(NSFont.systemFontOfSize_(12))
        show_record_btn.setTarget_(self)
        show_record_btn.setAction_("startRecordingShow:")
        c.addSubview_(show_record_btn)

        show_conflict = NSTextField.alloc().initWithFrame_(
            NSMakeRect(20, H-232, W-40, 16))
        show_conflict.setStringValue_("")
        show_conflict.setBezeled_(False); show_conflict.setDrawsBackground_(False)
        show_conflict.setEditable_(False)
        show_conflict.setFont_(NSFont.systemFontOfSize_(11))
        show_conflict.setTextColor_(NSColor.systemOrangeColor())
        c.addSubview_(show_conflict)

        # ── Cancel / Save ────────────────────────────────────────────────────
        cancel_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W-178, 16, 74, 28))
        cancel_btn.setTitle_("取消")
        cancel_btn.setBezelStyle_(NSBezelStyleRounded)
        cancel_btn.setButtonType_(NSButtonTypeMomentaryLight)
        cancel_btn.setFont_(NSFont.systemFontOfSize_(13))
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelSettings:")
        c.addSubview_(cancel_btn)

        save_btn = NSButton.alloc().initWithFrame_(NSMakeRect(W-96, 16, 76, 28))
        save_btn.setTitle_("保存")
        save_btn.setBezelStyle_(NSBezelStyleRounded)
        save_btn.setButtonType_(NSButtonTypeMomentaryLight)
        save_btn.setFont_(NSFont.systemFontOfSize_(13))
        save_btn.setTarget_(self)
        save_btn.setAction_("saveSettings:")
        save_btn.setKeyEquivalent_("\r")
        c.addSubview_(save_btn)

        self._window         = win
        self._hotkey_field   = hotkey_field
        self._conflict_label = conflict_label
        self._record_btn     = record_btn
        self._show_field     = show_field
        self._show_conflict  = show_conflict
        self._show_record_btn = show_record_btn

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
        NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
        self._window.orderFrontRegardless()
