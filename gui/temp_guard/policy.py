"""
Temp Guard interlock policy (no hardware drivers).

Composes Ads1115Reader / DS18B20Reader / DigitalAlarmReader and decides
whether pulses are allowed.
"""

from __future__ import annotations

from gui.temp_guard.ads1115 import Ads1115Reader
from gui.temp_guard.ds18b20 import DS18B20Reader
from gui.temp_guard.gpio_alarm import DigitalAlarmReader
from gui.temp_guard.types import (
    DEFAULT_GPIO_ALARM_PIN,
    SENSOR_ADS1115,
    SENSOR_CHOICES,
    SENSOR_DS18B20,
    SENSOR_GPIO_ALARM,
)

_ADS1115_DEFAULT_ADDR = 0x48


class TempGuard:
    """
    Unified temperature interlock used before GPIO pulses.

    When disabled: always allows pulses (no hardware use).
    When enabled: selected backend; blocks if over threshold / alarm HIGH,
    or if the sensor cannot be read (fail-safe).

    Install / wiring: gui/temp_guard/SETUP.md
    """

    def __init__(self, gpio=None):
        self.ads = Ads1115Reader()
        self.ds18b20 = DS18B20Reader()
        self.gpio_alarm = DigitalAlarmReader(gpio=gpio)
        self.last_error = None
        self.last_reading = None
        self.last_unit = None
        self._sensor_type = SENSOR_DS18B20
        self._gpio = gpio

    def configure(
        self,
        sensor_type=SENSOR_ADS1115,
        i2c_bus=1,
        i2c_address=_ADS1115_DEFAULT_ADDR,
        channel=0,
        ds18b20_id="",
        gpio_alarm_pin=DEFAULT_GPIO_ALARM_PIN,
        gpio=None,
    ):
        """Apply Settings values; does not force hardware open until read."""
        if gpio is not None:
            self._gpio = gpio
        self.ads.configure(
            i2c_bus=i2c_bus, i2c_address=i2c_address, channel=channel
        )
        self.ds18b20.configure(sensor_id=ds18b20_id)
        self.gpio_alarm.configure(pin=gpio_alarm_pin, gpio=self._gpio)
        self._sensor_type = sensor_type

    def close(self):
        self.ads.close()
        self.ds18b20.close()
        self.gpio_alarm.close()

    def read_current(self, sensor_type):
        """
        Read the active sensor.

        Returns (value, unit):
          DS18B20 → (°C, "C")
          ADS1115 → (volts, "V")
          GPIO alarm → (0 or 1, "ALARM")  where 1 = TEMP HIGH
          Failure → (None, None)
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

        if sensor_type == SENSOR_GPIO_ALARM:
            level = self.gpio_alarm.read_level()
            self.last_error = self.gpio_alarm.last_error
            if level is None:
                self.last_reading = None
                self.last_unit = None
                return None, None
            self.last_reading = level
            self.last_unit = "ALARM"
            return level, "ALARM"

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
        value, _unit = self.read_current(sensor_type)

        if value is None:
            if sensor_type == SENSOR_DS18B20:
                name = "DS18B20"
            elif sensor_type == SENSOR_GPIO_ALARM:
                name = "GPIO digital alarm"
            else:
                name = "ADS1115"
            msg = (
                f"Temp guard: cannot read {name}.\n"
                f"Detail: {self.last_error or 'unknown error'}\n"
                "Pulses are blocked until the sensor is available.\n"
                "See gui/temp_guard/SETUP.md for install & wiring."
            )
            return False, msg, None

        if sensor_type == SENSOR_GPIO_ALARM:
            if int(value) != 0:
                msg = (
                    "TEMP HIGH — pulse blocked.\n"
                    f"Digital alarm input is HIGH (BCM{self.gpio_alarm.pin})."
                )
                return False, msg, value
            return True, None, value

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
