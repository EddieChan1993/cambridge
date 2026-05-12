"""
NSApplicationDelegate — wires together the menu bar, hotkey, lookup pipeline
and the two windows (main + float panel).
"""

import os
import signal
import threading
import time
from pathlib import Path

import objc
from Foundation import NSObject
from AppKit import (
    NSApplication,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSPasteboard,
    NSStringPboardType,
    NSMenu,
    NSMenuItem,
    NSFont,
    NSAlert,
    NSAlertFirstButtonReturn,
)
import Quartz

from data_manager import DataManager
from main_window import MainWindowController
from float_panel import FloatPanel
from hotkey_monitor import HotkeyMonitor
from settings import Settings
from settings_window import SettingsWindowController
from utils import run_on_main_thread

_KEYCODE_C = 8          # always Cmd+C for clipboard simulation
_PID_FILE  = Path.home() / ".cambridge_tool" / "app.pid"


class _HotkeyShim(NSObject):
    """Routes hotkeyTriggered() to a Python callback, decoupling the two monitors."""

    @objc.python_method
    def setup(self, cb):
        self._cb = cb

    def hotkeyTriggered(self):
        if hasattr(self, "_cb"):
            self._cb()


class AppDelegate(NSObject):

    # ── NSApplicationDelegate ─────────────────────────────────────────────────

    def applicationDidFinishLaunching_(self, notification):
        self._enforceSingleInstance()

        self.data_manager   = DataManager()
        self.settings       = Settings()

        # ── 状态栏图标 ─────────────────────────────────────────────────────
        self._status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength)
        btn = self._status_item.button()
        btn.setTitle_("C")
        btn.setFont_(NSFont.boldSystemFontOfSize_(14))
        btn.setToolTip_("Cambridge 词典\n左键：显示主界面\n右键：菜单")

        # ── 右键菜单 ────────────────────────────────────────────────────────
        menu = NSMenu.alloc().init()
        menu.setDelegate_(self)     # menuWillOpen_ intercepts left-click

        item_prefs = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "偏好设置…", "openSettings:", "")
        item_prefs.setTarget_(self)
        menu.addItem_(item_prefs)

        menu.addItem_(NSMenuItem.separatorItem())

        item_quit = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出", "quitApp:", "")
        item_quit.setTarget_(self)
        menu.addItem_(item_quit)
        self._menu = menu
        self._status_item.setMenu_(menu)    # macOS handles right-click automatically

        # ── 窗口 ────────────────────────────────────────────────────────────
        self.main_window = MainWindowController.alloc().init()
        self.main_window._delegate = self

        self.float_panel = FloatPanel.alloc().init()
        self.float_panel._delegate = self

        # ── 偏好设置窗口（懒建）─────────────────────────────────────────────
        self._settings_win = SettingsWindowController.alloc(
            ).initWithSettings_delegate_(self.settings, self)

        # ── 全局快捷键：划词查询 ─────────────────────────────────────────────
        self._hotkey = HotkeyMonitor.alloc().initWithDelegate_keycode_modifiers_(
            self, self.settings.hotkey_keycode, self.settings.hotkey_modifiers)

        # ── 全局快捷键：呼出主界面 ───────────────────────────────────────────
        self._show_shim = _HotkeyShim.alloc().init()
        self._show_shim.setup(self._onShowWindowHotkey)
        self._show_hotkey = HotkeyMonitor.alloc().initWithDelegate_keycode_modifiers_(
            self._show_shim,
            self.settings.show_window_keycode,
            self.settings.show_window_modifiers,
        )

        # ── 主菜单（使 Cmd+C/V/X/A 在文本框中生效）──────────────────────────
        self._buildMainMenu()

        # ── 启动时显示主界面并填充列表 ───────────────────────────────────────
        self.main_window.refreshList()
        self.main_window.showWindow()

        self._checkAccessibility()

    def applicationShouldTerminateAfterLastWindowClosed_(self, app):
        return False

    def applicationWillTerminate_(self, notification):
        try:
            _PID_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # ── NSMenuDelegate — 拦截左键，让右键正常弹菜单 ───────────────────────────

    def menuWillOpen_(self, menu):
        from AppKit import NSApp
        event = NSApp.currentEvent()
        if event and event.type() == 1:     # NSEventTypeLeftMouseDown
            menu.cancelTracking()
            self._status_item.button().setHighlighted_(True)
            self.performSelector_withObject_afterDelay_(
                "_clearStatusHighlight:", None, 0.15)
            self.main_window.showWindow()

    @objc.IBAction
    def _clearStatusHighlight_(self, sender):
        self._status_item.button().setHighlighted_(False)

    @objc.IBAction
    def toggleMainWindow_(self, sender):
        self.main_window.toggleVisible()

    @objc.IBAction
    def openSettings_(self, sender):
        self._settings_win.showWindow()

    @objc.IBAction
    def quitApp_(self, sender):
        NSApplication.sharedApplication().terminate_(None)

    # ── 热键回调 ──────────────────────────────────────────────────────────────

    @objc.python_method
    def hotkeyTriggered(self):
        self.main_window.showWindow()
        word = self._getSelectedText()
        if word:
            word = word.strip()
        if word:
            self.lookupWordInMainWindow_(word)

    # ── 设置回调 ──────────────────────────────────────────────────────────────

    @objc.python_method
    def applyNewHotkey(self, keycode: int, modifiers: list):
        if self._hotkey:
            self._hotkey.stop()
        self._hotkey = HotkeyMonitor.alloc().initWithDelegate_keycode_modifiers_(
            self, keycode, modifiers)

    @objc.python_method
    def applyNewShowWindowHotkey(self, keycode: int, modifiers: list):
        if self._show_hotkey:
            self._show_hotkey.stop()
        self._show_hotkey = HotkeyMonitor.alloc().initWithDelegate_keycode_modifiers_(
            self._show_shim, keycode, modifiers)

    @objc.python_method
    def _onShowWindowHotkey(self):
        self.main_window.showWindow()

    # ── 查词流水线 ────────────────────────────────────────────────────────────

    def lookupWord_(self, word: str):
        word = word.strip()
        if not word:
            return
        self.float_panel.showWithWord_loading_(word, True)
        self._startLookup(word, target="panel")

    def lookupWordInMainWindow_(self, word: str):
        word = word.strip()
        if not word:
            return
        self.main_window.showLoadingForWord_(word)
        self._startLookup(word, target="main")

    @objc.python_method
    def _startLookup(self, word: str, target: str):
        def _run():
            from scraper import scrape_cambridge
            cached = self.data_manager.get_cached(word)
            result = cached if cached else scrape_cambridge(
                word, self.settings.lookup_base_url)
            has_entries = bool(result.get("entries"))
            if not cached and has_entries:
                self.data_manager.set_cached(word, result)
            if has_entries:
                self.data_manager.add_history(word)

            def _update():
                if target == "panel":
                    self.float_panel.updateWithResult_(result)
                else:
                    self.main_window.showContent_(result)
                    self.main_window.refreshHistory()
            run_on_main_thread(_update)

        threading.Thread(target=_run, daemon=True).start()

    @objc.python_method
    def refreshFavorites(self):
        self.main_window.refreshFavorites()

    # ── 读取选中文字 ──────────────────────────────────────────────────────────

    @objc.python_method
    def _getSelectedText(self) -> str:
        pb  = NSPasteboard.generalPasteboard()
        old = pb.stringForType_(NSStringPboardType) or ""

        src     = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
        keydown = Quartz.CGEventCreateKeyboardEvent(src, _KEYCODE_C, True)
        Quartz.CGEventSetFlags(keydown, Quartz.kCGEventFlagMaskCommand)
        keyup   = Quartz.CGEventCreateKeyboardEvent(src, _KEYCODE_C, False)
        Quartz.CGEventSetFlags(keyup, Quartz.kCGEventFlagMaskCommand)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, keydown)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, keyup)

        time.sleep(0.15)

        new = pb.stringForType_(NSStringPboardType) or ""
        if new != old and old:
            pb.clearContents()
            pb.setString_forType_(old, NSStringPboardType)

        word = new.strip()
        return "" if ("\n" in word or len(word) > 80) else word

    # ── 单实例 ────────────────────────────────────────────────────────────────

    @objc.python_method
    def _enforceSingleInstance(self):
        try:
            if _PID_FILE.exists():
                old_pid = int(_PID_FILE.read_text().strip())
                if old_pid != os.getpid():
                    try:
                        os.kill(old_pid, signal.SIGTERM)
                        time.sleep(0.3)
                    except ProcessLookupError:
                        pass
        except Exception:
            pass
        _PID_FILE.parent.mkdir(exist_ok=True)
        _PID_FILE.write_text(str(os.getpid()))

    # ── 主菜单 ────────────────────────────────────────────────────────────────

    @objc.python_method
    def _buildMainMenu(self):
        def _item(title, action, key, shift=False):
            it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, action, key)
            if shift:
                from AppKit import NSEventModifierFlagCommand, NSEventModifierFlagShift
                it.setKeyEquivalentModifierMask_(
                    NSEventModifierFlagCommand | NSEventModifierFlagShift)
            return it

        main_menu = NSMenu.alloc().init()

        app_item = NSMenuItem.alloc().init()
        main_menu.addItem_(app_item)
        app_menu = NSMenu.alloc().init()
        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "退出", "terminate:", "q")
        quit_item.setTarget_(NSApplication.sharedApplication())
        app_menu.addItem_(quit_item)
        app_item.setSubmenu_(app_menu)

        edit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "编辑", None, "")
        main_menu.addItem_(edit_item)
        edit_menu = NSMenu.alloc().initWithTitle_("编辑")
        edit_menu.addItem_(_item("撤销",  "undo:",      "z"))
        edit_menu.addItem_(_item("重做",  "redo:",      "z", shift=True))
        edit_menu.addItem_(NSMenuItem.separatorItem())
        edit_menu.addItem_(_item("剪切",  "cut:",       "x"))
        edit_menu.addItem_(_item("拷贝",  "copy:",      "c"))
        edit_menu.addItem_(_item("粘贴",  "paste:",     "v"))
        edit_menu.addItem_(NSMenuItem.separatorItem())
        edit_menu.addItem_(_item("全选",  "selectAll:", "a"))
        edit_item.setSubmenu_(edit_menu)

        NSApplication.sharedApplication().setMainMenu_(main_menu)

    # ── 辅助功能权限 ──────────────────────────────────────────────────────────

    @objc.python_method
    def _checkAccessibility(self):
        # AXTrustedCheckOptionPrompt=True 让系统自动弹出辅助功能授权对话框
        trusted = Quartz.AXIsProcessTrustedWithOptions(
            {"AXTrustedCheckOptionPrompt": True})
        if not trusted:
            lookup_str = self.settings.hotkey_display_string()
            show_str   = self.settings.show_window_display_string()
            alert = NSAlert.alloc().init()
            alert.setMessageText_("需要辅助功能权限以启用全局快捷键")
            alert.setInformativeText_(
                f"快捷键（{lookup_str} 划词查询、{show_str} 呼出界面）"
                "需要辅助功能权限。\n\n"
                "系统已弹出授权对话框，请在「系统设置 → 隐私与安全性 → 辅助功能」"
                "中勾选本应用，然后重启应用即可生效。"
            )
            alert.addButtonWithTitle_("好的")
            alert.addButtonWithTitle_("打开系统设置")
            if alert.runModal() != NSAlertFirstButtonReturn:
                from AppKit import NSWorkspace
                from Foundation import NSURL
                NSWorkspace.sharedWorkspace().openURL_(
                    NSURL.URLWithString_(
                        "x-apple.systempreferences:"
                        "com.apple.preference.security?Privacy_Accessibility"))
