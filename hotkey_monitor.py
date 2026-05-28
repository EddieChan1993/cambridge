# Copyright © 2026 EddieChan1993. All rights reserved.
# Unauthorized commercial use is strictly prohibited.
"""
Global hotkey monitor — CGEventTap with NSEvent global monitor fallback.
Plain Python class (no NSObject) to avoid PyObjC init-method pitfalls.
Initialization is deferred via run_on_main_thread so the run loop is ready.
"""

import Quartz
from AppKit import NSEvent, NSEventMaskKeyDown

# ── Debug log ─────────────────────────────────────────────────────────────────

def _log(msg):
    with open("/tmp/hotdict_init.log", "a", encoding="utf-8") as f:
        f.write(msg + "\n")

with open("/tmp/hotdict_init.log", "w", encoding="utf-8") as _f:
    _f.write("hotkey_monitor imported\n")

# ── Modifier maps ─────────────────────────────────────────────────────────────

_QUARTZ_MODS = {
    "cmd":   Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "alt":   Quartz.kCGEventFlagMaskAlternate,
    "ctrl":  Quartz.kCGEventFlagMaskControl,
}

_NS_MODS = {
    "cmd":   0x100000,
    "shift": 0x020000,
    "alt":   0x080000,
    "ctrl":  0x040000,
}


class HotkeyMonitor:

    def __init__(self, delegate, keycode, modifiers):
        self._delegate   = delegate
        self._keycode    = int(keycode)
        self._modifiers  = set(modifiers)
        self._tap        = None
        self._tap_cb     = None   # GC anchor for CGEventTap callback
        self._tap_src    = None   # GC anchor for CFRunLoopSource
        self._ns_handler = None   # GC anchor for NSEvent handler
        self._monitor    = None

        _log(f"init kc={keycode} mods={list(modifiers)}")

        # Defer until run loop is running
        from utils import run_on_main_thread
        monitor = self
        run_on_main_thread(lambda: monitor._start())

    def stop(self):
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None
        if self._monitor:
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _start(self):
        _log(f"_start kc={self._keycode} mods={self._modifiers}")
        if not self._try_event_tap():
            _log("CGEventTap unavailable, falling back to NSEvent monitor")
            self._try_ns_monitor()

    def _matches(self, keycode: int, flags: int) -> bool:
        if keycode != self._keycode:
            return False
        for mod, mask in _QUARTZ_MODS.items():
            if bool(flags & mask) != (mod in self._modifiers):
                return False
        return True

    def _try_event_tap(self) -> bool:
        mon = self

        def _cb(proxy, event_type, event, refcon):
            try:
                if event_type in (
                    Quartz.kCGEventTapDisabledByUserInput,
                    Quartz.kCGEventTapDisabledByTimeout,
                ):
                    if mon._tap:
                        Quartz.CGEventTapEnable(mon._tap, True)
                    return event
                if event_type == Quartz.kCGEventKeyDown:
                    kc    = Quartz.CGEventGetIntegerValueField(
                        event, Quartz.kCGKeyboardEventKeycode)
                    flags = Quartz.CGEventGetFlags(event)
                    if mon._matches(int(kc), int(flags)):
                        mon._fire()
                        return None
            except Exception as exc:
                _log(f"tap cb error: {exc}")
            return event

        try:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap,
                Quartz.kCGHeadInsertEventTap,
                Quartz.kCGEventTapOptionDefault,
                Quartz.CGEventMaskBit(Quartz.kCGEventKeyDown),
                _cb,
                None,
            )
            _log(f"CGEventTapCreate → {tap}")
            if not tap:
                return False
            self._tap    = tap
            self._tap_cb = _cb   # prevent GC
            src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._tap_src = src  # prevent GC
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetMain(), src, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            return True
        except Exception as exc:
            _log(f"CGEventTap exception: {exc}")
            return False

    def _try_ns_monitor(self):
        mon = self

        def _handler(event):
            try:
                kc       = event.keyCode()
                raw      = event.modifierFlags()
                ns_flags = sum(
                    _QUARTZ_MODS[m] for m, mask in _NS_MODS.items()
                    if raw & mask
                )
                _log(f"NS keydown kc={kc} flags={hex(ns_flags)}")
                if mon._matches(int(kc), int(ns_flags)):
                    mon._fire()
            except Exception as exc:
                _log(f"NS handler error: {exc}")

        self._ns_handler = _handler   # prevent GC
        self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, _handler)
        _log(f"NSEvent monitor → {self._monitor}")

    def _fire(self):
        _log("_fire called")
        from utils import run_on_main_thread
        run_on_main_thread(lambda: self._delegate.hotkeyTriggered())
