# panahon-solar-ha

DOST-PAGASA weather forecast and solar PV planning for Home Assistant.

The official DOST-PAGASA PANaHON mobile app has the most accurate forecast data for the Philippines, but the app itself is laggy and bloated on phones. I sniffed its API and hooked it up with ECMWF solar irradiance so I can pull real-time weather, heat index, and tomorrow's solar yield straight into Home Assistant for solar battery planning.

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=panahon_solar)

---

## What It Does

- Pulls live weather, heat index, and active storm alerts straight from DOST-PAGASA (`api.mobile.panahon.gov.ph`).
- Calculates solar irradiance on your roof (GHI + GTI) based on your coordinates, tilt, and roof azimuth.
- Estimates real-time solar PV generation and rooftop panel heat loss (-0.35%/°C above 25°C).
- Forecasts tomorrow's total kWh harvest so you know how much battery to save overnight.
- Gives a battery advisory entity (e.g. hold 90% reserve when a typhoon is flagged or high rain is coming).
- No API token required. Works out of the box with zero setup hassle.
- 100% reconfigurable from the HA UI anytime (change your coordinates or array size from **Configure**).

---

## Installation

### Method 1: HACS (Recommended)

1. Open **HACS** in Home Assistant.
2. Click the 3 dots in the top right -> **Custom repositories**.
3. Paste `https://github.com/hinzwifi/panahon-solar-ha` and pick category **Integration**.
4. Click **Download**, then restart Home Assistant.
5. Click this button to add it, or search for `DOST-PAGASA PANaHON` in **Settings** -> **Devices & Services**:

[![Open your Home Assistant instance and start setting up a new integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=panahon_solar)

### Method 2: Manual Install

1. Clone or download this repo:
   ```bash
   git clone https://github.com/hinzwifi/panahon-solar-ha.git
   ```
2. Copy `custom_components/panahon_solar` into your Home Assistant `/config/custom_components/` folder:
   ```
   /config/custom_components/panahon_solar
   ```
3. Restart Home Assistant.
4. Add the integration from **Settings** -> **Devices & Services** -> **Add Integration**.

---

## Setup

Setup has 2 simple screens:

1. **Step 1: Location & Solar Array**
   - **Name**: Pick any name (default: `PANaHON PH Solar`).
   - **Latitude & Longitude**: Pre-filled with your HA location (or type your exact coordinates).
   - **Solar PV Array Capacity**: Your solar panel capacity in kWp (e.g. `5.0`).
   - **Panel Tilt**: Roof tilt angle in degrees (default `14°` works great for PH).

2. **Step 2: Roof Facing & Advanced**
   - **Panel Azimuth**: `0°` for South, `90°` for West, `-90°` for East.
   - **System Efficiency**: Default `0.82` (82% inverter/wiring efficiency).
   - **Device ID & Token**: Leave empty unless you have custom PANaHON station bearer tokens.

### Changing Settings Later
Click **Configure** on the integration card anytime to change your lat/lon, array kWp, or angles. It updates your sensors immediately without having to delete and re-add.

---

## How to Verify It's Working

1. Go to **Developer Tools** -> **States**.
2. Filter by `panahon`.
3. Check these entities:
   - `weather.panahon_ph_forecast`: 5-day daily forecast and condition.
   - `sensor.panahon_resolved_location`: Exact barangay/city resolved by PAGASA.
   - `sensor.panahon_pagasa_heat_index`: Heat index °C with `pagasa_danger_level` attribute.
   - `sensor.panahon_estimated_pv_power`: Current solar PV output in kW.
   - `sensor.panahon_tomorrow_forecasted_pv_energy`: Expected kWh harvest tomorrow.

---

## Entities

| Entity ID | Unit | Description |
| :--- | :--- | :--- |
| `weather.panahon_ph_forecast` | - | 5-day forecast and condition |
| `sensor.panahon_resolved_location` | - | Resolved municipality & barangay |
| `sensor.panahon_weather_condition` | - | Live PAGASA condition text |
| `sensor.panahon_solar_radiation_ghi` | W/m² | Horizontal solar irradiance |
| `sensor.panahon_roof_tilted_irradiance_gti` | W/m² | Tilted irradiance on your roof |
| `sensor.panahon_estimated_pv_power` | kW | Real-time solar power |
| `sensor.panahon_today_forecasted_pv_energy` | kWh | Expected total harvest today |
| `sensor.panahon_tomorrow_forecasted_pv_energy` | kWh | Expected total harvest tomorrow |
| `sensor.panahon_peak_sun_hours_today` | h | Peak sun hours |
| `sensor.panahon_pv_cell_temperature` | °C | Rooftop panel temperature |
| `sensor.panahon_tropical_thermal_derating` | % | Power reduction from heat |
| `sensor.panahon_pagasa_heat_index` | °C | Heat index & danger level |
| `sensor.panahon_1h_rainfall` | mm | Last hour rainfall |
| `sensor.panahon_cloud_cover` | % | Cloud cover percentage |
| `sensor.panahon_wind_speed` | km/h | 10m wind speed |
| `sensor.panahon_barometric_pressure` | hPa | Pressure |
| `sensor.panahon_solar_and_typhoon_battery_advisory` | - | Battery reserve advisory |

---

## Automations & Lovelace Cards

Check out the [`home_assistant_integration/`](./home_assistant_integration/) folder for sample automations (AC precooling, EV charger detection, 12kW inverter redline alerts) and Lovelace cards.
