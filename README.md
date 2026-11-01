# ☀️ PANaHON-Solar-HA

DOST-PAGASA weather forecast and solar PV planning integration for Home Assistant.

The official DOST-PAGASA PANaHON mobile app has the most accurate forecast for the Philippines, but the app itself is super laggy and bloated on modern phones. I reverse-engineered its internal API and ECMWF numerical forecast engine so I could pull live weather, solar irradiance, and tomorrow's harvest directly into Home Assistant for my solar setup and battery planning.

## Features

- **No Lag, Pure Home Assistant**: Ditch the mobile app and get live updates straight to your dashboard.
- **DOST-PAGASA Heat Index**: Computes accurate Philippine heat index and danger classifications (Caution, Extreme Caution, Danger, Extreme Danger).
- **Solar Irradiance (GHI & GTI)**: Provides both Global Horizontal Irradiance and Global Tilted Irradiance on your roof tilt angle (W/m²).
- **Real-Time PV Power & Tropical Derating**: Models actual panel temperature ($T_{cell}$) and power loss ($-0.35\%/^\circ\text{C}$) during hot Philippine midday sun.
- **Tomorrow's Forecasted Harvest**: Predicts tomorrow's total kWh yield so your inverter knows how much battery reserve to hold overnight.
- **Typhoon & Heavy Rain Guard**: Advises when to hold 85-90% battery reserve ahead of severe storms and grid blackouts.
- **Zero Token Needed**: Works out-of-the-box using the same ECMWF tropical forecast model that PANaHON uses, with optional support for authorized PANaHON station tokens.

## Tech Stack

- **Home Assistant**: Custom Component (Integration + Config Flow + Weather + Sensor platforms)
- **Engine**: Python 3, aiohttp, ECMWF IFS Numerical Weather Prediction, DOST-PAGASA AWS telemetry

## Installation

### Method 1: Manual Copy

1. Clone or download this repo:
   ```bash
   git clone https://github.com/hinzwifi/panahon-solar-ha.git
   ```
2. Copy the folder `custom_components/panahon_solar` into your Home Assistant directory:
   ```
   /config/custom_components/panahon_solar
   ```
3. Restart Home Assistant.
4. In Home Assistant, go to **Settings** → **Devices & Services** → **Add Integration**.
5. Search for **DOST-PAGASA PANaHON & PH Solar Forecast** and enter your latitude, longitude, and solar array size (kWp).

### Method 2: HACS Custom Repository

1. Open HACS in Home Assistant.
2. Click the 3 dots in the top right → **Custom repositories**.
3. Add `https://github.com/hinzwifi/panahon-solar-ha` with category **Integration**.
4. Click **Download**, restart Home Assistant, and add it under Integrations.

## Available Sensors

| Entity ID | Name | Unit | Description |
| :--- | :--- | :--- | :--- |
| `weather.panahon_ph_forecast` | PANaHON PH Forecast | - | 5-day weather condition & temp forecast |
| `sensor.panahon_solar_radiation_ghi` | Solar Radiation (GHI) | W/m² | Global horizontal solar irradiance |
| `sensor.panahon_roof_tilted_irradiance_gti` | Roof Tilted Irradiance (GTI) | W/m² | Irradiance adjusted for your roof tilt & azimuth |
| `sensor.panahon_estimated_pv_power` | Estimated PV Power | kW | Real-time PV output with heat derating |
| `sensor.panahon_today_forecasted_pv_energy` | Today Forecasted PV Yield | kWh | Total expected energy generation today |
| `sensor.panahon_tomorrow_forecasted_pv_energy` | Tomorrow Forecasted PV Yield | kWh | Tomorrow's solar harvest forecast |
| `sensor.panahon_peak_sun_hours_today` | Peak Sun Hours Today | h | Equivalent full-sun hours |
| `sensor.panahon_pv_cell_temperature` | PV Cell Temperature | °C | Rooftop panel temperature |
| `sensor.panahon_tropical_thermal_derating` | Tropical Thermal Derating | % | Output reduction due to tropical heat |
| `sensor.panahon_pagasa_heat_index` | PAGASA Heat Index | °C | Philippine apparent temperature + danger level |
| `sensor.panahon_solar_and_typhoon_battery_advisory` | Typhoon & Battery Advisory | - | Smart battery reserve recommendations |
| `sensor.panahon_1h_rainfall` | 1h Rainfall | mm | Hourly rainfall depth |
| `sensor.panahon_cloud_cover` | Cloud Cover | % | Cloud cover percentage |
| `sensor.panahon_wind_speed` | Wind Speed | km/h | 10m wind speed |
| `sensor.panahon_barometric_pressure` | Barometric Pressure | hPa | Atmospheric pressure |

## Solar AI Automation & Dashboard Card

Check out the [`home_assistant_integration/`](./home_assistant_integration/) folder for:
- Pre-made automations for precooling ACs during high solar and preserving morning battery reserve.
- Sleek Lovelace UI cards with 12kW inverter overload guard and 7kW EV charger detection.

## Acknowledgements

- **DOST-PAGASA** for official Philippine weather observations and data.
- **ECMWF** for the numerical weather prediction models.
- **Home Assistant** community.

## Author

- @hinzwifi https://www.github.com/hinzwifi
