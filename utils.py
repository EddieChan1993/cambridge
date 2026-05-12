"""
Thread-safe main-thread dispatcher and shared helpers.
"""

import threading
from Foundation import NSObject
import objc


class _Dispatcher(NSObject):
    """Tiny ObjC helper so we can bounce a Python callable to the main thread."""

    def runBlock_(self, block):
        block()


_dispatcher_lock = threading.Lock()
_dispatcher: "_Dispatcher | None" = None


def _get_dispatcher() -> "_Dispatcher":
    global _dispatcher
    with _dispatcher_lock:
        if _dispatcher is None:
            _dispatcher = _Dispatcher.alloc().init()
    return _dispatcher


def run_on_main_thread(func, wait: bool = False):
    """
    Schedule *func* to run on the main thread.  Safe to call from any thread.
    If *wait* is True the call blocks until *func* completes.
    """
    _get_dispatcher().performSelectorOnMainThread_withObject_waitUntilDone_(
        "runBlock:", func, wait
    )
