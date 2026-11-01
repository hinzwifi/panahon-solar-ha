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
- **100% Reconfigurable via UI**: Change panel tilt, azimuth, or array size on the fly anytime using the Home Assistant **Configure** button.

## Tech Stack

- **Home Assistant**: Custom Component (Integration + Config Flow + Options Flow + Weather + Sensor platforms)
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
5. Search for **DOST-PAGASA PANaHON & PH Solar Forecast**.

### Method 2: HACS Custom Repository

1. Open HACS in Home Assistant.
2. Click the 3 dots in the top right → **Custom repositories**.
3. Add `https://github.com/hinzwifi/panahon-solar-ha` with category **Integration**.
4. Click **Download**, restart Home Assistant, and add it under Integrations.

## Setup Wizard (KISS & Step-by-Step)

The setup is split into two dead-simple steps:

- **Step 1: Location & Solar Array (Required)**
  - **Name**: Defaults to `PANaHON PH Solar`
  - **Latitude & Longitude**: Automatically pre-filled with your Home Assistant home coordinates.
  - **Solar Array Capacity (kWp)**: Enter your system's total DC panel rating (e.g. `5.0`).
  - **Roof Panel Tilt**: Defaults to `14°` (optimal for Philippine solar latitude).

- **Step 2: Roof Orientation & Station Link (Optional)**
  - **Panel Azimuth**: `0°` for South-facing roofs (`90°` for West, `-90°` for East).
  - **System Efficiency**: Defaults to `0.82` (82% inverter & wiring efficiency).
  - **PANaHON Device ID & Token**: Leave completely blank! It automatically queries the official ECMWF tropical forecast model with zero credentials.

### How to Reconfigure Later

Need to update your array kWp or change angles?
- Go to **Settings** → **Devices & Services** → click **Configure** on the PANaHON integration card.
- Tweak your values and hit Submit. Home Assistant updates your sensors immediately without reloading or deleting anything.

## How to Verify It's Working (60 Seconds)

1. In Home Assistant, go to **Developer Tools** → **States**.
2. In the filter box, type `panahon`.
3. Check the following entities:
   - `weather.panahon_ph_forecast`: Shows live weather condition and 5-day daily forecast.
   - `sensor.panahon_pagasa_heat_index`: Displays live apparent temperature and the attribute `pagasa_danger_level`.
   - `sensor.panahon_estimated_pv_power`: Shows current real-time PV generation in kW.
   - `sensor.panahon_tomorrow_forecasted_pv_energy`: Shows expected kWh harvest tomorrow.

If these display numbers, the integration is 100% active and working.

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
