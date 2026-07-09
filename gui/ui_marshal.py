"""
Marshal work onto the Tk main thread (Phase 3).

Non-UI threads must not touch widgets, tk variables, or messagebox.
Use ui_call(root, fn, ...) instead.
"""

from __future__ import annotations

import threading


def on_ui_thread(root) -> bool:
    """Best-effort check: Tk apps run the event loop on the main thread."""
    try:
        return threading.current_thread() is threading.main_thread()
    except Exception:
        return False


def ui_call(root, fn, *args, **kwargs):
    """
    Schedule ``fn(*args, **kwargs)`` on the Tk event loop.

    If already on the main thread, runs immediately (avoids after latency
    for code that is sometimes called from UI handlers).
    """
    if root is None:
        fn(*args, **kwargs)
        return

    if on_ui_thread(root):
        fn(*args, **kwargs)
        return

    def _runner():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            print(f"ui_call error in {getattr(fn, '__name__', fn)}: {e}")

    try:
        root.after(0, _runner)
    except Exception:
        # Root may be destroyed during shutdown
        pass


def ui_call_later(root, delay_ms, fn, *args, **kwargs):
    """Like ui_call but always uses after(delay_ms, ...)."""
    if root is None:
        return

    def _runner():
        try:
            fn(*args, **kwargs)
        except Exception as e:
            print(f"ui_call_later error in {getattr(fn, '__name__', fn)}: {e}")

    try:
        root.after(int(delay_ms), _runner)
    except Exception:
        pass
