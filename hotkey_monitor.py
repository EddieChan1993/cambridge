"""
Global hotkey via Carbon RegisterEventHotKey (ctypes).
No Accessibility / Input Monitoring permission required.
"""

import ctypes
import ctypes.util

import objc
from Foundation import NSObject

# ── Carbon ctypes bindings ────────────────────────────────────────────────────

_carbon = ctypes.CDLL(ctypes.util.find_library("Carbon"))

# Carbon modifier masks (different from CGEvent masks)
_CARBON_MODS = {
    "cmd":   0x0100,
    "shift": 0x0200,
    "alt":   0x0800,
    "ctrl":  0x1000,
}

kEventClassKeyboard  = 0x6B657973   # 'keys'
kEventHotKeyPressed  = 5
kEventParamDirectObject = 0x2D2D2D2D  # '----'
typeEventHotKeyID    = 0x686B6579   # 'hkey'
_HK_SIGNATURE        = 0x48444B59   # 'HDKY'
noErr                = 0


class _EventHotKeyID(ctypes.Structure):
    _fields_ = [("signature", ctypes.c_uint32), ("id", ctypes.c_uint32)]


class _EventTypeSpec(ctypes.Structure):
    _fields_ = [("eventClass", ctypes.c_uint32), ("eventKind", ctypes.c_uint32)]


_HandlerProc = ctypes.CFUNCTYPE(
    ctypes.c_int32,    # OSStatus
    ctypes.c_void_p,   # EventHandlerCallRef
    ctypes.c_void_p,   # EventRef
    ctypes.c_void_p,   # userData
)

# Explicit argtypes so ctypes passes structures correctly (by value vs by pointer)
_carbon.GetApplicationEventTarget.restype  = ctypes.c_void_p
_carbon.GetApplicationEventTarget.argtypes = []

_carbon.InstallEventHandler.restype  = ctypes.c_int32
_carbon.InstallEventHandler.argtypes = [
    ctypes.c_void_p,                    # inTarget
    ctypes.c_void_p,                    # inHandler (function ptr)
    ctypes.c_uint32,                    # inNumTypes
    ctypes.POINTER(_EventTypeSpec),     # inList
    ctypes.c_void_p,                    # inUserData
    ctypes.c_void_p,                    # outRef (can be NULL)
]

_carbon.RegisterEventHotKey.restype  = ctypes.c_int32
_carbon.RegisterEventHotKey.argtypes = [
    ctypes.c_uint32,                    # inHotKeyCode
    ctypes.c_uint32,                    # inHotKeyModifiers
    _EventHotKeyID,                     # inHotKeyID  (passed by value)
    ctypes.c_void_p,                    # inTarget
    ctypes.c_uint32,                    # inOptions
    ctypes.POINTER(ctypes.c_void_p),    # outRef
]

_carbon.UnregisterEventHotKey.restype  = ctypes.c_int32
_carbon.UnregisterEventHotKey.argtypes = [ctypes.c_void_p]

_carbon.GetEventParameter.restype  = ctypes.c_int32
_carbon.GetEventParameter.argtypes = [
    ctypes.c_void_p,   # inEvent
    ctypes.c_uint32,   # inName
    ctypes.c_uint32,   # inDesiredType
    ctypes.c_void_p,   # outActualType (NULL ok)
    ctypes.c_size_t,   # inBufferSize
    ctypes.c_void_p,   # outActualSize (NULL ok)
    ctypes.c_void_p,   # outData
]

# ── Module-level handler (one handler for all registered hotkeys) ─────────────

_registry: dict[int, "HotkeyMonitor"] = {}
_handler_installed = False


def _on_hotkey(call_ref, event_ref, user_data):
    hkid = _EventHotKeyID()
    _carbon.GetEventParameter(
        event_ref,
        kEventParamDirectObject,
        typeEventHotKeyID,
        None,
        ctypes.sizeof(hkid),
        None,
        ctypes.byref(hkid),
    )
    monitor = _registry.get(hkid.id)
    if monitor is not None:
        monitor._fire()
    return noErr


def _ensure_handler():
    global _handler_installed
    if _handler_installed:
        return

    target = _carbon.GetApplicationEventTarget()
    if not target:
        print("[HotkeyMonitor] GetApplicationEventTarget returned NULL — skipping")
        return

    spec = _EventTypeSpec(kEventClassKeyboard, kEventHotKeyPressed)
    cb   = _HandlerProc(_on_hotkey)
    _ensure_handler._cb = cb   # keep Python ref so GC won't collect the callback

    status = _carbon.InstallEventHandler(
        target,
        cb,
        ctypes.c_uint32(1),
        ctypes.byref(spec),
        None,
        None,
    )
    if status == noErr:
        _handler_installed = True
        print("[HotkeyMonitor] Carbon event handler installed")
    else:
        print(f"[HotkeyMonitor] InstallEventHandler failed: {status}")


# ── Public class (same interface as before) ───────────────────────────────────

_next_id = 1


class HotkeyMonitor(NSObject):

    def initWithDelegate_keycode_modifiers_(self, delegate, keycode, modifiers):
        self = objc.super(HotkeyMonitor, self).init()
        if self is None:
            return None
        global _next_id
        self._delegate   = delegate
        self._keycode    = int(keycode)
        self._modifiers  = list(modifiers)
        self._hk_id      = _next_id
        _next_id        += 1
        self._ref        = ctypes.c_void_p()
        self._registered = False
        self._register()
        return self

    @objc.python_method
    def stop(self):
        if self._registered:
            _carbon.UnregisterEventHotKey(self._ref)
            _registry.pop(self._hk_id, None)
            self._registered = False

    @objc.python_method
    def _register(self):
        _ensure_handler()
        if not _handler_installed:
            print("[HotkeyMonitor] handler not ready, hotkey skipped")
            return

        mod_mask = ctypes.c_uint32(
            sum(_CARBON_MODS.get(m, 0) for m in self._modifiers))
        hkid   = _EventHotKeyID(signature=_HK_SIGNATURE, id=self._hk_id)
        target = _carbon.GetApplicationEventTarget()

        status = _carbon.RegisterEventHotKey(
            ctypes.c_uint32(self._keycode),
            mod_mask,
            hkid,
            target,
            ctypes.c_uint32(0),
            ctypes.byref(self._ref),
        )
        if status == noErr:
            _registry[self._hk_id] = self
            self._registered = True
            print(f"[HotkeyMonitor] registered id={self._hk_id} "
                  f"kc={self._keycode} mods={self._modifiers}")
        else:
            print(f"[HotkeyMonitor] RegisterEventHotKey failed status={status}")

    @objc.python_method
    def _fire(self):
        from utils import run_on_main_thread
        run_on_main_thread(lambda: self._delegate.hotkeyTriggered())
