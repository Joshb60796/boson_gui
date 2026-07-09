"""
DS18B20 1-Wire temperature driver (Linux w1-therm sysfs).

Install: dtoverlay=w1-gpio, 4.7k pull-up; no pip package.
Wiring: see gui/temp_guard/SETUP.md (OPTION A).
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

_W1_DEVICES = Path("/sys/bus/w1/devices")


class DS18B20Reader:
    """
    Read temperature (°C) from a DS18B20 via Linux w1-therm sysfs.

    Requires:
      - 1-Wire enabled: dtoverlay=w1-gpio in config.txt, then reboot
      - 4.7 kΩ pull-up from DATA to 3V3
    Kernel exposes: /sys/bus/w1/devices/28-*/w1_slave
    """

    def __init__(self, sensor_id=""):
        self.sensor_id = (sensor_id or "").strip()
        self._lock = threading.Lock()
        self.last_error = None
        self.last_celsius = None
        self.available = False

    def configure(self, sensor_id=None):
        with self._lock:
            if sensor_id is not None:
                self.sensor_id = (sensor_id or "").strip()

    def close(self):
        pass

    @staticmethod
    def list_sensors():
        """Return sorted list of connected DS18B20 IDs (28-...)."""
        if not _W1_DEVICES.is_dir():
            return []
        return sorted(p.name for p in _W1_DEVICES.glob("28-*") if p.is_dir())

    def _resolve_device_dir(self):
        if self.sensor_id:
            path = _W1_DEVICES / self.sensor_id
            if path.is_dir():
                return path
            self.last_error = f"Sensor not found: {self.sensor_id}"
            return None

        sensors = self.list_sensors()
        if not sensors:
            self.last_error = (
                "No DS18B20 found under /sys/bus/w1/devices. "
                "Enable 1-Wire (dtoverlay=w1-gpio), wire 4.7k pull-up, reboot."
            )
            return None
        return _W1_DEVICES / sensors[0]

    def read_celsius(self):
        """Return temperature in °C, or None on failure (see last_error)."""
        with self._lock:
            if not _W1_DEVICES.is_dir():
                self.last_error = (
                    "1-Wire sysfs missing (/sys/bus/w1/devices). "
                    "Add dtoverlay=w1-gpio and reboot."
                )
                self.last_celsius = None
                self.available = False
                return None

            device_dir = self._resolve_device_dir()
            if device_dir is None:
                self.last_celsius = None
                self.available = False
                return None

            slave = device_dir / "w1_slave"
            try:
                for _ in range(2):
                    text = slave.read_text()
                    lines = text.strip().splitlines()
                    if len(lines) < 2:
                        time.sleep(0.2)
                        continue
                    if not lines[0].strip().endswith("YES"):
                        time.sleep(0.2)
                        continue
                    if "t=" not in lines[1]:
                        time.sleep(0.2)
                        continue
                    milli = int(lines[1].split("t=")[1].strip())
                    celsius = milli / 1000.0
                    self.last_celsius = celsius
                    self.last_error = None
                    self.available = True
                    return celsius

                self.last_error = "DS18B20 CRC/read failed"
                self.last_celsius = None
                self.available = False
                return None
            except Exception as e:
                self.last_error = str(e)
                self.last_celsius = None
                self.available = False
                return None
