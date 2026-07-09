"""
ADS1115 I2C ADC driver for thermistor voltage dividers.

Install: enable I2C, pip install smbus2
Wiring: see gui/temp_guard/SETUP.md (OPTION B).
"""

from __future__ import annotations

import threading
import time

_ADS1115_DEFAULT_ADDR = 0x48
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01
_PGA_4_096 = 0x0200
_PGA_FS_VOLTS = 4.096
_MUX_SINGLE = {0: 0x4000, 1: 0x5000, 2: 0x6000, 3: 0x7000}


class Ads1115Reader:
    """
    Read single-ended voltage from an ADS1115 ADC over I2C.

    Requires: I2C enabled on the Pi,  pip install smbus2
    Import:   from smbus2 import SMBus  (loaded lazily in _open_unlocked)
    """

    def __init__(self, i2c_bus=1, i2c_address=_ADS1115_DEFAULT_ADDR, channel=0):
        self.i2c_bus = int(i2c_bus)
        self.i2c_address = int(i2c_address)
        self.channel = int(channel) % 4
        self._bus = None
        self._lock = threading.Lock()
        self.last_error = None
        self.last_voltage = None
        self.available = False

    def configure(self, i2c_bus=None, i2c_address=None, channel=None):
        """Update I2C parameters; bus re-opens lazily on next read."""
        with self._lock:
            reopen = False
            if i2c_bus is not None and int(i2c_bus) != self.i2c_bus:
                self.i2c_bus = int(i2c_bus)
                reopen = True
            if i2c_address is not None and int(i2c_address) != self.i2c_address:
                self.i2c_address = int(i2c_address)
                reopen = True
            if channel is not None:
                self.channel = int(channel) % 4
            if reopen:
                self._close_unlocked()

    def _close_unlocked(self):
        if self._bus is not None:
            try:
                self._bus.close()
            except Exception:
                pass
            self._bus = None
        self.available = False

    def close(self):
        with self._lock:
            self._close_unlocked()

    def _open_unlocked(self):
        if self._bus is not None:
            return
        try:
            from smbus2 import SMBus

            bus = SMBus(self.i2c_bus)
            bus.read_i2c_block_data(self.i2c_address, _REG_CONFIG, 2)
            self._bus = bus
            self.available = True
            self.last_error = None
            print(
                f"Temp guard ADS1115 ready @ 0x{self.i2c_address:02X} "
                f"bus {self.i2c_bus} AIN{self.channel}"
            )
        except ImportError:
            self._bus = None
            self.available = False
            self.last_error = (
                "smbus2 not installed. Run:  pip install smbus2  "
                "(and enable I2C on the Pi)"
            )
        except Exception as e:
            self._bus = None
            self.available = False
            self.last_error = str(e)

    def read_voltage(self):
        """Single-shot AINx vs GND. Returns volts, or None on failure."""
        with self._lock:
            self._open_unlocked()
            if self._bus is None:
                self.last_voltage = None
                return None
            try:
                mux = _MUX_SINGLE.get(self.channel, _MUX_SINGLE[0])
                config = (
                    0x8000
                    | mux
                    | _PGA_4_096
                    | 0x0100
                    | 0x0080
                    | 0x0003
                )
                self._bus.write_i2c_block_data(
                    self.i2c_address,
                    _REG_CONFIG,
                    [(config >> 8) & 0xFF, config & 0xFF],
                )
                for _ in range(20):
                    time.sleep(0.008)
                    cfg = self._bus.read_i2c_block_data(
                        self.i2c_address, _REG_CONFIG, 2
                    )
                    if cfg[0] & 0x80:
                        break
                data = self._bus.read_i2c_block_data(
                    self.i2c_address, _REG_CONVERSION, 2
                )
                raw = (data[0] << 8) | data[1]
                if raw >= 0x8000:
                    raw -= 0x10000
                voltage = raw / 32768.0 * _PGA_FS_VOLTS
                self.last_voltage = voltage
                self.last_error = None
                self.available = True
                return voltage
            except Exception as e:
                self.last_error = str(e)
                self.last_voltage = None
                self.available = False
                self._close_unlocked()
                return None
