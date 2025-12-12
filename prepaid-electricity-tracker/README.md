# Prepaid Electricity Tracker

A comprehensive Home Assistant integration for tracking prepaid electricity usage with South African tiered tariff calculations, designed for use with Deye inverters and Sonoff smart breakers.

## Features

- **Real-time Power Monitoring**: Track instantaneous power consumption from grid
- **Balance Tracking**: Monitor remaining prepaid electricity units (kWh)
- **Tiered Tariff Calculations**: Automatic calculation based on South African electricity tariff structures
- **Dual Inverter Support**: Designed for configurations with multiple Deye inverters
- **Smart Breaker Integration**: Works with Sonoff smart breakers for detailed consumption data
- **Cost Projections**: Estimate daily, weekly, and monthly electricity costs
- **Low Balance Alerts**: Configurable notifications when units are running low

## Hardware Requirements

- Home Assistant instance
- Deye inverter(s) with monitoring capability
- Sonoff smart breaker (e.g., POWR3, SPM-Main)
- WiFi connectivity for all devices

## Installation

1. Copy the integration files to your Home Assistant `custom_components` directory
2. Restart Home Assistant
3. Configure via the UI or YAML

### YAML Configuration

```yaml
sensor:
  - platform: prepaid_electricity
    name: "Prepaid Electricity"
    initial_balance: 500  # Starting kWh balance
    tariff_structure: "eskom_homeflex"
    power_sensor: sensor.sonoff_power
    
automation:
  - alias: "Low Electricity Warning"
    trigger:
      - platform: numeric_state
        entity_id: sensor.prepaid_electricity_balance
        below: 50
    action:
      - service: notify.mobile_app
        data:
          title: "Low Electricity"
          message: "Only {{ states('sensor.prepaid_electricity_balance') }} kWh remaining"
```

## Supported Tariff Structures

- Eskom Homeflex
- Eskom Homelight
- Municipal tiered rates (configurable)
- Custom tariff definitions

## Dashboard Card

Include a Lovelace card for easy monitoring:

```yaml
type: entities
title: Prepaid Electricity
entities:
  - entity: sensor.prepaid_electricity_balance
    name: Remaining Units
  - entity: sensor.prepaid_electricity_daily_usage
    name: Today's Usage
  - entity: sensor.prepaid_electricity_cost_today
    name: Today's Cost
  - entity: sensor.prepaid_electricity_projected_monthly
    name: Projected Monthly Cost
```

## Integration with Deye Inverters

The tracker can pull grid consumption data directly from your Deye inverter(s) for more accurate tracking when solar is also in use.

```yaml
sensor:
  - platform: prepaid_electricity
    power_sensor: sensor.deye_grid_power
    export_sensor: sensor.deye_grid_export  # Optional: for net metering
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - See [LICENSE](../LICENSE) for details.
