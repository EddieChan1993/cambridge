"""
Global hotkey monitor — configurable keycode + modifier set.
Uses Quartz CGEventTap (requires Accessibility / Input Monitoring permission).
Falls back to NSEvent global monitor if the tap cannot be created.
"""

import objc
from Foundation import NSObject
import Quartz

# Quartz modifier-flag constants mapped from settings mod names
_QUARTZ_MODS = {
    "cmd":   Quartz.kCGEventFlagMaskCommand,
    "shift": Quartz.kCGEventFlagMaskShift,
    "alt":   Quartz.kCGEventFlagMaskAlternate,
    "ctrl":  Quartz.kCGEventFlagMaskControl,
}

# NSEvent modifier flag values (same numeric values as Quartz)
_NS_MODS = {
    "cmd":   0x100000,
    "shift": 0x020000,
    "alt":   0x080000,
    "ctrl":  0x040000,
}


class HotkeyMonitor(NSObject):
    """
    initWithDelegate_keycode_modifiers_  — pass an object with a hotkeyTriggered method,
    the virtual key-code (int), and a list of modifier names from {"cmd","shift","alt","ctrl"}.
    """

    def initWithDelegate_keycode_modifiers_(self, delegate, keycode, modifiers):
        self = objc.super(HotkeyMonitor, self).init()
        if self is None:
            return None
        self._delegate  = delegate
        self._keycode   = int(keycode)
        self._modifiers = set(modifiers)
        self._tap       = None
        self._monitor   = None
        self._running   = False
        self._start()
        return self

    # ── Public ───────────────────────────────────────────────────────────────

    def stop(self):
        self._running = False
        if self._tap:
            Quartz.CGEventTapEnable(self._tap, False)
            self._tap = None
        if self._monitor:
            from AppKit import NSEvent
            NSEvent.removeMonitor_(self._monitor)
            self._monitor = None

    # ── Internal ─────────────────────────────────────────────────────────────

    @objc.python_method
    def _start(self):
        print(f"[HotkeyMonitor] starting — keycode={self._keycode} mods={self._modifiers}")
        ok = self._try_event_tap()
        print(f"[HotkeyMonitor] CGEventTap created: {ok}")
        if not ok:
            self._try_ns_monitor()
            print("[HotkeyMonitor] fell back to NSEvent global monitor")

    @objc.python_method
    def _matches(self, keycode: int, flags: int) -> bool:
        if keycode != self._keycode:
            return False
        for mod, mask in _QUARTZ_MODS.items():
            has  = bool(flags & mask)
            want = mod in self._modifiers
            if has != want:
                return False
        return True

    @objc.python_method
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
                    print(f"[HotkeyMonitor] keydown kc={kc} flags={hex(int(flags))} want_kc={mon._keycode} want_mods={mon._modifiers}")
                if mon._matches(int(kc), int(flags)):
                        mon._fire()
                        return None     # consume
            except Exception as exc:
                print(f"[HotkeyMonitor] callback error: {exc}")
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
            if not tap:
                return False
            self._tap = tap
            self._tap_callback = _cb   # keep Python ref so GC won't collect it
            src = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            self._tap_src = src        # keep run-loop source alive too
            Quartz.CFRunLoopAddSource(
                Quartz.CFRunLoopGetMain(), src, Quartz.kCFRunLoopCommonModes)
            Quartz.CGEventTapEnable(tap, True)
            self._running = True
            return True
        except Exception as exc:
            print(f"[HotkeyMonitor] CGEventTap failed: {exc}")
            return False

    @objc.python_method
    def _try_ns_monitor(self):
        from AppKit import NSEvent, NSEventMaskKeyDown
        mon = self

        def _handler(event):
            try:
                kc    = event.keyCode()
                flags = event.modifierFlags()
                ns_flags = 0
                for mod, mask in _NS_MODS.items():
                    if flags & mask:
                        ns_flags |= _QUARTZ_MODS[mod]
                print(f"[HotkeyMonitor][NS] keydown kc={kc} ns_flags={hex(ns_flags)}")
                if mon._matches(int(kc), int(ns_flags)):
                    mon._fire()
            except Exception as exc:
                print(f"[HotkeyMonitor] NSEvent monitor error: {exc}")

        self._ns_handler = _handler   # keep Python ref
        self._monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            NSEventMaskKeyDown, _handler)
        print(f"[HotkeyMonitor] NSEvent monitor registered: {self._monitor is not None}")
        self._running = True

    @objc.python_method
    def _fire(self):
        from utils import run_on_main_thread
        run_on_main_thread(lambda: self._delegate.hotkeyTriggered())
