# Temp Guard — install & wiring

Leave **Temp Guard** unchecked until hardware is wired and **Read Now** works.

When **disabled**: no sensor I/O; pulses never blocked for temperature.  
When **enabled**: failed sensor read also blocks pulses (fail-safe).

---

## Quick start

1. Wire the chosen sensor.
2. Settings → Temp Guard → pick type (DS18B20, ADS1115, or GPIO alarm).
3. Set threshold (Max °C / Max V) or alarm BCM pin.
4. **Read Now** / **List sensors**.
5. Enable **Temp Guard — block pulses when over temperature**.

---

## OPTION A — DS18B20 (1-Wire °C)

Digital thermometer. Typical setpoints 20–80 °C (sensor ~−55…+125 °C).

**OS**

```text
# /boot/firmware/config.txt  (or /boot/config.txt)
dtoverlay=w1-gpio
# optional: dtoverlay=w1-gpio,gpiopin=4
```

Reboot. No pip package — uses `/sys/bus/w1/devices/28-*/w1_slave`.

**Wiring (3.3 V only)**

```text
Red    → 3V3
Black  → GND
Yellow → GPIO data (e.g. BCM4) + 4.7 kΩ pull-up to 3V3
```

**Check**

```bash
ls /sys/bus/w1/devices/
cat /sys/bus/w1/devices/28-xxxxxxxxxxxx/w1_slave
```

---

## OPTION B — ADS1115 + thermistor (I2C voltage)

Pi GPIO has no ADC. ADS1115 digitizes a thermistor divider.

**OS**

- Enable I2C (`raspi-config`), reboot  
- `pip install smbus2`  
- `sudo i2cdetect -y 1` (often `0x48` → addr **72** decimal in Settings)

**Wiring**

```text
3V3 --[ Rf ]--+--[ NTC ]-- GND
              |
           ADS1115 AIN0

ADS1115: VDD→3V3, GND→GND, SDA→BCM2, SCL→BCM3
```

Block when voltage **> Max V**. Orient divider so “too hot” raises the mid-point voltage.

PGA in software: ±4.096 V (safe for 0–3.3 V).

---

## OPTION C — Arduino / digital alarm (GPIO input)

External controller drives a line **HIGH** when temperature is too high.

**Default pin:** BCM **16** (`DEFAULT_GPIO_ALARM_PIN`)

Avoids: 17 (button), 22/23/24/27 (default pulses), 2/3 (I2C), 4 (1-Wire), 14/15 (UART).

**Wiring**

```text
Arduino DO (3.3 V) → Pi BCM16
Arduino GND        → Pi GND
```

**3.3 V logic only** — not 5 V Arduino levels without a level shifter.

Software uses shared `GpioService` with pull-down (open = LOW = no alarm). Arduino must drive HIGH for TEMP HIGH.

---

## Related code

| Module | Role |
|--------|------|
| `gui/temp_guard/policy.py` | Interlock decision |
| `gui/temp_guard/ads1115.py` | ADS1115 driver |
| `gui/temp_guard/ds18b20.py` | DS18B20 driver |
| `gui/temp_guard/gpio_alarm.py` | Digital alarm driver |
| `gui/temp_guard_controller.py` | UI status + pulse gate |
| `gui/gpio_service.py` | Shared GPIO chip |
