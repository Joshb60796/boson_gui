"""
Temperature interlock package (Phase 5: drivers vs policy).

Public API (unchanged for importers)::

    from gui.temp_guard import (
        TempGuard,
        Ads1115Reader,
        DS18B20Reader,
        DigitalAlarmReader,
        SENSOR_ADS1115,
        SENSOR_DS18B20,
        SENSOR_GPIO_ALARM,
        SENSOR_CHOICES,
    )

Install / wiring: ``gui/temp_guard/SETUP.md``.

Layout
------
- types.py       — sensor type string constants
- ads1115.py     — I2C ADC driver
- ds18b20.py     — 1-Wire driver
- gpio_alarm.py  — digital alarm input driver
- policy.py      — TempGuard interlock policy
"""

from gui.temp_guard.ads1115 import Ads1115Reader
from gui.temp_guard.ds18b20 import DS18B20Reader
from gui.temp_guard.gpio_alarm import DigitalAlarmReader
from gui.temp_guard.policy import TempGuard
from gui.temp_guard.types import (
    DEFAULT_GPIO_ALARM_PIN,
    SENSOR_ADS1115,
    SENSOR_CHOICES,
    SENSOR_DS18B20,
    SENSOR_GPIO_ALARM,
)

__all__ = [
    "Ads1115Reader",
    "DS18B20Reader",
    "DigitalAlarmReader",
    "TempGuard",
    "SENSOR_ADS1115",
    "SENSOR_DS18B20",
    "SENSOR_GPIO_ALARM",
    "SENSOR_CHOICES",
    "DEFAULT_GPIO_ALARM_PIN",
]
