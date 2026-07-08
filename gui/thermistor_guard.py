"""
Backward-compatible re-export.

Temp Guard lives in gui/temp_guard.py (ADS1115 + DS18B20, install & wiring notes).
Prefer:

    from gui.temp_guard import TempGuard, Ads1115Reader, DS18B20Reader
"""

from gui.temp_guard import Ads1115Reader as ThermistorGuard  # noqa: F401
from gui.temp_guard import TempGuard  # noqa: F401
