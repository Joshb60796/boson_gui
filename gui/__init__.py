"""Boson+ radiometric GUI package.

Import the app from gui.app to avoid loading camera/GPIO deps at package import time:

    from gui.app import main, BosonApp
"""

__all__ = ["BosonApp", "main"]


def __getattr__(name):
    if name in ("BosonApp", "main"):
        from gui.app import BosonApp, main
        return BosonApp if name == "BosonApp" else main
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
