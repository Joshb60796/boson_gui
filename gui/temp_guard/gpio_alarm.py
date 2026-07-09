"""
Digital active-HIGH temperature alarm input (e.g. Arduino → Pi GPIO).

Uses shared GpioService (gui.gpio_service). Wiring: SETUP.md OPTION C.
"""

from __future__ import annotations

import threading

from gui.temp_guard.types import DEFAULT_GPIO_ALARM_PIN


class DigitalAlarmReader:
    """
    Active-HIGH digital temperature alarm on a Pi BCM GPIO.

    HIGH (1) → alarm (TEMP HIGH), block pulses.
    LOW  (0) → OK.
    Registers on shared GpioService with pull-down.
    """

    def __init__(self, pin=DEFAULT_GPIO_ALARM_PIN, gpio=None):
        self.pin = int(pin)
        self.gpio = gpio
        self._lock = threading.Lock()
        self._registered = False
        self.last_error = None
        self.last_level = None
        self.available = False

    def configure(self, pin=None, gpio=None):
        with self._lock:
            if gpio is not None:
                self.gpio = gpio
            if pin is not None and int(pin) != self.pin:
                self._unregister_unlocked()
                self.pin = int(pin)

    def _unregister_unlocked(self):
        if self._registered and self.gpio is not None:
            try:
                self.gpio.unregister(self.pin)
            except Exception:
                pass
        self._registered = False
        self.available = False

    def close(self):
        with self._lock:
            self._unregister_unlocked()

    def _ensure_registered_unlocked(self):
        if self.gpio is None:
            self.last_error = "GpioService not set (app must pass shared GPIO)"
            self.available = False
            return False
        if self._registered:
            return True
        try:
            from gui.gpio_service import PinRole

            self.gpio.register_input(
                self.pin, PinRole.TEMP_ALARM, pull_down=True
            )
            self._registered = True
            self.available = True
            self.last_error = None
            print(f"Temp guard digital alarm ready on BCM{self.pin} (active HIGH)")
            return True
        except Exception as e:
            self._registered = False
            self.available = False
            self.last_error = str(e)
            return False

    def read_level(self):
        """Return 1 if alarm HIGH, 0 if LOW, or None on failure."""
        with self._lock:
            if not self._ensure_registered_unlocked():
                self.last_level = None
                return None
            try:
                level = int(self.gpio.read(self.pin))
                self.last_level = 1 if level else 0
                self.last_error = None
                self.available = True
                return self.last_level
            except Exception as e:
                self.last_error = str(e)
                self.last_level = None
                self.available = False
                self._unregister_unlocked()
                return None
