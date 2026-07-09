"""Temp Guard sensor type keys (stored in config.json → temp_guard_sensor)."""

SENSOR_ADS1115 = "ads1115"
SENSOR_DS18B20 = "ds18b20"
SENSOR_GPIO_ALARM = "gpio_alarm"  # Arduino (or other) 3.3 V digital HIGH = alarm
SENSOR_CHOICES = (SENSOR_ADS1115, SENSOR_DS18B20, SENSOR_GPIO_ALARM)

# Default BCM pin for digital alarm — keep free of button / pulses / I2C / UART.
# See constants.DEFAULT_GPIO_ALARM_PIN and SETUP.md OPTION C.
DEFAULT_GPIO_ALARM_PIN = 16
