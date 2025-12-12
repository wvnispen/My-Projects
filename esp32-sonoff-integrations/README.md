# ESP32 & Sonoff Integrations

Custom configurations, firmware, and automations for ESP32 and Sonoff devices integrated with Home Assistant.

## Projects

### ESPHome Configurations

Custom ESPHome configurations for various ESP32-based devices and Sonoff products.

### Sonoff Devices

Configurations and automations for:
- **Sonoff POW R3** - Power monitoring smart switch
- **Sonoff SPM-Main** - Smart stackable power meter
- **Sonoff Basic** - WiFi smart switch
- **Sonoff Mini** - Compact WiFi smart switch

## Directory Structure

```
esp32-sonoff-integrations/
├── esphome/
│   ├── esp32-power-monitor.yaml
│   ├── esp32-temp-humidity.yaml
│   └── ...
├── sonoff/
│   ├── powr3-config.yaml
│   ├── spm-main-config.yaml
│   └── ...
├── automations/
│   └── power-automations.yaml
└── dashboards/
    └── energy-dashboard.yaml
```

## ESPHome Example

```yaml
esphome:
  name: power-monitor
  platform: ESP32
  board: esp32dev

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

sensor:
  - platform: hlw8012
    sel_pin: GPIO12
    cf_pin: GPIO5
    cf1_pin: GPIO14
    current:
      name: "Current"
    voltage:
      name: "Voltage"
    power:
      name: "Power"
    energy:
      name: "Energy"
    update_interval: 10s
```

## Sonoff POW R3 Configuration

```yaml
substitutions:
  device_name: sonoff-powr3
  friendly_name: "Power Monitor"

esphome:
  name: ${device_name}
  platform: ESP32
  board: nodemcu-32s

# ... full configuration in sonoff/powr3-config.yaml
```

## Home Assistant Automations

Example automation for load shedding preparation:

```yaml
automation:
  - alias: "Pre-Loadshedding Battery Charge"
    trigger:
      - platform: state
        entity_id: binary_sensor.loadshedding_coming
        to: "on"
    action:
      - service: switch.turn_on
        entity_id: switch.inverter_grid_charge
```

## Flashing Sonoff Devices

### Requirements
- USB-to-Serial adapter (3.3V)
- ESPHome or Tasmota firmware
- Soldering iron (for some models)

### Process
1. Open the device and locate programming pins
2. Connect USB-to-Serial adapter
3. Hold button while powering on to enter flash mode
4. Flash using ESPHome CLI or web interface

## Contributing

Feel free to submit your own configurations and automations!

## License

MIT License - See [LICENSE](../LICENSE) for details.
