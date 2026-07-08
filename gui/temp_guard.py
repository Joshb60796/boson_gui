"""
Temperature interlock backends for pulse blocking (Temp Guard).

==============================================================================
QUICK START (in the GUI)
==============================================================================
1. Leave "Temp Guard" UNCHECKED until hardware is wired and tested.
2. Settings → Temp Guard → pick sensor type (DS18B20 or ADS1115).
3. Set the threshold (Max °C or Max V).
4. Click "Read Now" / "List sensors" to verify a live reading.
5. Only then enable "Temp Guard — block pulses when over temperature".

When disabled: no sensor I/O is required; pulses are never blocked for temp.
When enabled: a failed sensor read ALSO blocks pulses (fail-safe).

==============================================================================
OPTION A — DS18B20 (1-Wire digital thermometer)  [recommended for °C limits]
==============================================================================
What it is:
  Digital temp sensor on the Linux 1-Wire bus. Reports true temperature in °C.
  Typical setpoints in this app: 20–80 °C (sensor itself supports ~−55…+125 °C).

Software / OS (Raspberry Pi):
  - Enable 1-Wire, e.g. in /boot/firmware/config.txt (or /boot/config.txt):
        dtoverlay=w1-gpio
    (optional pin: dtoverlay=w1-gpio,gpiopin=4  — GPIO4 / BCM4 is common)
  - Reboot after changing overlays.
  - No extra pip package is required. This code reads the kernel sysfs driver:
        /sys/bus/w1/devices/28-*/w1_slave
  - Optional check on the Pi:
        ls /sys/bus/w1/devices/
        cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave

Python imports used:
  - pathlib, threading, time (stdlib only for DS18B20 path)

Wiring (3.3 V logic — do NOT use 5 V on Pi GPIO data):
  DS18B20 pinout varies by package; for a common waterproof probe:
      Red    → 3V3
      Black  → GND
      Yellow → GPIO data (e.g. BCM4) AND a 4.7 kΩ pull-up to 3V3

  Always install a ~4.7 kΩ resistor between DATA and 3V3.
  Keep cable runs reasonable; long cables may need stronger pull-up / care.

Multiple sensors:
  Each has an ID like 28-00000xxxxxxx. Leave "ID" blank to use the first found,
  or paste a specific ID from "List sensors".

==============================================================================
OPTION B — ADS1115 + thermistor voltage divider  [analog via I2C ADC]
==============================================================================
Why an ADC:
  Raspberry Pi 5 GPIO pins are digital-only. They cannot measure analog voltage.
  An ADS1115 converts the thermistor divider voltage to a digital reading over I2C.

Software / OS (Raspberry Pi):
  - Enable I2C: sudo raspi-config → Interface Options → I2C → Yes  (then reboot)
  - Install Python package:
        pip install smbus2
    (imported only when ADS1115 is opened:  from smbus2 import SMBus)
  - Optional check:
        sudo i2cdetect -y 1
    You should see the ADS1115 address (often 0x48 → enter 72 decimal in Settings).

Python imports used:
  - smbus2.SMBus  (third-party; install as above)
  - threading, time (stdlib)

Default I2C parameters in this project:
  - Bus: 1 (standard on Pi)
  - Address: 0x48 (72 decimal) — change ADDR pins on the module for 0x49–0x4B
  - Channel: AIN0 (0–3)

Wiring example (3.3 V thermistor divider → AIN0):

      3V3 ----[ fixed resistor Rf ]----+----[ NTC thermistor ]---- GND
                                       |
                                    ADS1115 AIN0

  ADS1115 module to Pi:
      VDD → 3V3
      GND → GND
      SDA → SDA (BCM2)
      SCL → SCL (BCM3)
      (ADDR → GND for address 0x48 on many breakout boards)

  Choose Rf so the mid-point voltage at your trip temperature is easy to set
  as "Max V" in Settings. This app blocks when voltage > Max V, so orient the
  divider (NTC top vs bottom) so "too hot" means HIGHER voltage — or invert
  the physical divider if your circuit goes the other way.

PGA:
  Code uses ±4.096 V full-scale (safe for 0–3.3 V dividers).

==============================================================================
BEHAVIOR / SAFETY
==============================================================================
- Threshold compare: reading > limit  →  block pulse + error dialog.
- Sensor read failure while Temp Guard is ON → block pulse (fail-safe).
- Status line on main UI updates about once per second only when enabled.
- Pulse paths all go through BosonApp.trigger_pulse() → _pulse_allowed().

Related files:
  gui/temp_guard.py     — this module (readers + interlock logic)
  gui/settings.py       — Temp Guard UI
  gui/app.py            — enable check before GPIO pulses
  gui/config_io.py      — persists temp_guard_* settings in config.json
  gui/constants.py      — defaults
"""

from __future__ import annotations

import threading
import time
from pathlib import Path


# Sensor type keys stored in config.json → temp_guard_sensor
SENSOR_ADS1115 = "ads1115"
SENSOR_DS18B20 = "ds18b20"
SENSOR_CHOICES = (SENSOR_ADS1115, SENSOR_DS18B20)

# ---------------------------------------------------------------------------
# ADS1115 register map (I2C ADC — see module docstring for wiring/install)
# ---------------------------------------------------------------------------
_ADS1115_DEFAULT_ADDR = 0x48  # ADDR pin to GND on most breakouts
_REG_CONVERSION = 0x00
_REG_CONFIG = 0x01
_PGA_4_096 = 0x0200  # ±4.096 V FSR
_PGA_FS_VOLTS = 4.096
# Single-ended MUX encodings: AINx versus GND
_MUX_SINGLE = {0: 0x4000, 1: 0x5000, 2: 0x6000, 3: 0x7000}

# ---------------------------------------------------------------------------
# DS18B20 via Linux w1-therm (enable dtoverlay=w1-gpio; no pip package needed)
# ---------------------------------------------------------------------------
_W1_DEVICES = Path("/sys/bus/w1/devices")


class Ads1115Reader:
    """
    Read single-ended voltage from an ADS1115 ADC over I2C.

    Requires: I2C enabled on the Pi,  pip install smbus2
    Import:   from smbus2 import SMBus  (loaded lazily in _open_unlocked)
    Wiring:   see module docstring "OPTION B — ADS1115".
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
            # Lazy: open on next read (no I2C traffic until then)

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
            # Third-party: pip install smbus2
            from smbus2 import SMBus

            bus = SMBus(self.i2c_bus)
            # Probe device by reading config register
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
        """
        Single-shot read of AINx vs GND.

        Returns voltage in volts, or None on failure (see last_error).
        """
        with self._lock:
            self._open_unlocked()
            if self._bus is None:
                self.last_voltage = None
                return None
            try:
                mux = _MUX_SINGLE.get(self.channel, _MUX_SINGLE[0])
                # OS start | MUX | PGA ±4.096 | single-shot | 128 SPS | comp off
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


class DS18B20Reader:
    """
    Read temperature (°C) from a DS18B20 via Linux w1-therm sysfs.

    Requires:
      - 1-Wire enabled: dtoverlay=w1-gpio in config.txt, then reboot
      - 4.7 kΩ pull-up from DATA to 3V3
      - Sensor powered (or parasite power — VDD/GND/DATA wiring preferred)
    No pip package. Kernel exposes: /sys/bus/w1/devices/28-*/w1_slave
    Wiring: see module docstring "OPTION A — DS18B20".
    """

    def __init__(self, sensor_id=""):
        # Empty sensor_id → use first 28-* device found
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
        """
        Return sorted list of connected DS18B20 IDs (names like 28-00000a1b2c3d).

        Empty list usually means: overlay not loaded, wrong GPIO, missing pull-up,
        or sensor not detected. Check: ls /sys/bus/w1/devices/
        """
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
                # Two attempts: CRC can fail if read mid-conversion
                for _ in range(2):
                    text = slave.read_text()
                    lines = text.strip().splitlines()
                    if len(lines) < 2:
                        time.sleep(0.2)
                        continue
                    if not lines[0].strip().endswith("YES"):
                        time.sleep(0.2)
                        continue
                    # Second line ends with t=25562 meaning 25.562 °C
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


class TempGuard:
    """
    Unified temperature interlock used by BosonApp before GPIO pulses.

    When temp_guard_enabled is False: always allows pulses (no hardware use).
    When True: uses selected backend (ads1115 | ds18b20) and blocks if over
    threshold or if the sensor cannot be read.

    Setup checklist is in the module docstring at the top of this file.
    """

    def __init__(self):
        self.ads = Ads1115Reader()
        self.ds18b20 = DS18B20Reader()
        self.last_error = None
        self.last_reading = None  # float: volts or °C
        self.last_unit = None  # "V" or "C"
        self._sensor_type = SENSOR_DS18B20

    def configure(
        self,
        sensor_type=SENSOR_ADS1115,
        i2c_bus=1,
        i2c_address=_ADS1115_DEFAULT_ADDR,
        channel=0,
        ds18b20_id="",
    ):
        """Apply Settings values; does not force a hardware open until read."""
        self.ads.configure(
            i2c_bus=i2c_bus, i2c_address=i2c_address, channel=channel
        )
        self.ds18b20.configure(sensor_id=ds18b20_id)
        self._sensor_type = sensor_type

    def close(self):
        self.ads.close()
        self.ds18b20.close()

    def read_current(self, sensor_type):
        """
        Read the active sensor.

        Returns (value, unit) where unit is "V" or "C", or (None, None) on failure.
        """
        if sensor_type == SENSOR_DS18B20:
            value = self.ds18b20.read_celsius()
            self.last_error = self.ds18b20.last_error
            if value is None:
                self.last_reading = None
                self.last_unit = None
                return None, None
            self.last_reading = value
            self.last_unit = "C"
            return value, "C"

        # Default / ADS1115 thermistor voltage
        value = self.ads.read_voltage()
        self.last_error = self.ads.last_error
        if value is None:
            self.last_reading = None
            self.last_unit = None
            return None, None
        self.last_reading = value
        self.last_unit = "V"
        return value, "V"

    def check_allows_pulse(
        self,
        enabled: bool,
        sensor_type: str,
        threshold_v: float,
        threshold_c: float,
    ):
        """
        Returns (allowed: bool, message: str | None, reading: float | None).

        When Temp Guard is disabled, always allows (no hardware access).
        """
        if not enabled:
            return True, None, None

        sensor_type = sensor_type if sensor_type in SENSOR_CHOICES else SENSOR_ADS1115
        value, unit = self.read_current(sensor_type)

        if value is None:
            name = "DS18B20" if sensor_type == SENSOR_DS18B20 else "ADS1115"
            msg = (
                f"Temp guard: cannot read {name}.\n"
                f"Detail: {self.last_error or 'unknown error'}\n"
                "Pulses are blocked until the sensor is available.\n"
                "See comments in gui/temp_guard.py for install & wiring."
            )
            return False, msg, None

        if sensor_type == SENSOR_DS18B20:
            limit = float(threshold_c)
            if value > limit:
                msg = (
                    "Temperature too high — pulse blocked.\n"
                    f"DS18B20: {value:.2f} °C (limit: {limit:.1f} °C)"
                )
                return False, msg, value
            return True, None, value

        limit = float(threshold_v)
        if value > limit:
            msg = (
                "Temperature too high — pulse blocked.\n"
                f"Thermistor voltage: {value:.3f} V (limit: {limit:.3f} V)"
            )
            return False, msg, value
        return True, None, value
