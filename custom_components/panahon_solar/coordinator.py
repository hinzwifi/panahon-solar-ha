"""DataUpdateCoordinator for DOST-PAGASA PANaHON & PH Solar Forecast."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_LATITUDE, CONF_LONGITUDE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_ACCESS_TOKEN,
    CONF_ARRAY_KWP,
    CONF_DEVICE_ID,
    CONF_PANEL_AZIMUTH,
    CONF_PANEL_TILT,
    CONF_SYS_EFFICIENCY,
    DEFAULT_ARRAY_KWP,
    DEFAULT_PANEL_AZIMUTH,
    DEFAULT_PANEL_TILT,
    DEFAULT_SYS_EFFICIENCY,
    DOMAIN,
    PANAHON_BASE_URL,
)

_LOGGER = logging.getLogger(__name__)
PH_TZ = timezone(timedelta(hours=8))


def _calculate_heat_index(temp_c: float, rh_pct: float) -> tuple[float, str]:
    if temp_c < 26.0 or rh_pct < 40.0:
        hi_c = temp_c
    else:
        t_f = temp_c * 9.0 / 5.0 + 32.0
        r = rh_pct
        hi_f = (
            -42.379
            + 2.04901523 * t_f
            + 10.14333127 * r
            - 0.22475541 * t_f * r
            - 0.00683783 * t_f * t_f
            - 0.05481717 * r * r
            + 0.00122874 * t_f * t_f * r
            + 0.00085282 * t_f * r * r
            - 0.00000199 * t_f * t_f * r * r
        )
        hi_c = (hi_f - 32.0) * 5.0 / 9.0

    hi_c = round(hi_c, 1)
    if hi_c >= 52.0:
        return hi_c, "Extreme Danger"
    if hi_c >= 42.0:
        return hi_c, "Danger"
    if hi_c >= 33.0:
        return hi_c, "Extreme Caution"
    if hi_c >= 27.0:
        return hi_c, "Caution"
    return hi_c, "Normal"


def _compute_pv(
    irradiance_wm2: float,
    air_temp_c: float,
    array_kwp: float,
    sys_eff: float,
) -> tuple[float, float, float]:
    g = max(0.0, float(irradiance_wm2))
    if g <= 0.0:
        return round(air_temp_c, 1), 0.0, 0.0
    cell_temp = air_temp_c + ((45.0 - 20.0) / 800.0) * g
    delta_t = max(0.0, cell_temp - 25.0)
    thermal_factor = max(0.50, min(1.05, 1.0 - 0.0035 * delta_t))
    derating_pct = round((1.0 - thermal_factor) * 100.0, 2)
    pv_kw = round(min(array_kwp, max(0.0, array_kwp * (g / 1000.0) * sys_eff * thermal_factor)), 3)
    return round(cell_temp, 1), derating_pct, pv_kw


class PanahonSolarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator fetching PANaHON / ECMWF PH weather and solar irradiance."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=15),
        )
        self.entry = entry
        self._etag_by_url: dict[str, str] = {}
        self._body_by_url: dict[str, dict[str, Any]] = {}

    async def _async_update_data(self) -> dict[str, Any]:
        session = async_get_clientsession(self.hass)
        config = {**self.entry.data, **self.entry.options}
        lat = float(config.get(CONF_LATITUDE, 14.5995))
        lon = float(config.get(CONF_LONGITUDE, 120.9842))
        array_kwp = float(config.get(CONF_ARRAY_KWP, DEFAULT_ARRAY_KWP))
        tilt = float(config.get(CONF_PANEL_TILT, DEFAULT_PANEL_TILT))
        azimuth = float(config.get(CONF_PANEL_AZIMUTH, DEFAULT_PANEL_AZIMUTH))
        sys_eff = float(config.get(CONF_SYS_EFFICIENCY, DEFAULT_SYS_EFFICIENCY))
        device_id = str(config.get(CONF_DEVICE_ID, "")).strip()
        access_token = str(config.get(CONF_ACCESS_TOKEN, "")).strip()

        panahon_obs: dict[str, Any] = {}
        if device_id and access_token:
            obs_url = f"{PANAHON_BASE_URL}/observation/automatic"
            headers = {
                "X-Device-Id": device_id,
                "Authorization": f"Bearer {access_token}",
            }
            if obs_url in self._etag_by_url:
                headers["If-None-Match"] = self._etag_by_url[obs_url]
            try:
                async with session.get(obs_url, headers=headers, timeout=10) as resp:
                    if resp.status == 200:
                        panahon_obs = await resp.json()
                        etag = resp.headers.get("ETag")
                        if etag:
                            self._etag_by_url[obs_url] = etag
                            self._body_by_url[obs_url] = panahon_obs
                    elif resp.status == 304:
                        panahon_obs = self._body_by_url.get(obs_url, {})
            except Exception as err:
                _LOGGER.debug("PANaHON mobile observation fallback triggered: %s", err)

        params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "Asia/Manila",
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,cloud_cover,pressure_msl,"
                "wind_speed_10m,wind_direction_10m,shortwave_radiation,"
                "direct_normal_irradiance,diffuse_radiation,global_tilted_irradiance"
            ),
            "hourly": (
                "temperature_2m,precipitation,precipitation_probability,"
                "cloud_cover,shortwave_radiation,global_tilted_irradiance"
            ),
            "daily": (
                "weather_code,temperature_2m_max,temperature_2m_min,"
                "precipitation_sum,precipitation_probability_max,"
                "wind_speed_10m_max,shortwave_radiation_sum"
            ),
            "tilt": tilt,
            "azimuth": azimuth,
            "forecast_days": 5,
        }
        try:
            async with session.get(
                "https://api.open-meteo.com/v1/forecast", params=params, timeout=15
            ) as resp:
                if resp.status != 200:
                    raise UpdateFailed(f"Upstream forecast error: HTTP {resp.status}")
                ecmwf = await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with forecast upstream: {err}") from err

        curr = ecmwf.get("current", {})
        hourly = ecmwf.get("hourly", {})
        daily = ecmwf.get("daily", {})

        air_temp = float(panahon_obs.get("air_temperature_avg") or curr.get("temperature_2m", 30.0))
        rh = float(panahon_obs.get("relative_humidity_avg") or curr.get("relative_humidity_2m", 70.0))
        ghi = float(panahon_obs.get("solar_radiation_avg") or curr.get("shortwave_radiation", 0.0))
        gti = float(curr.get("global_tilted_irradiance", ghi))
        precip_1h = float(panahon_obs.get("rainfall") or curr.get("precipitation", 0.0))
        cloud_cover = float(curr.get("cloud_cover", 0.0))
        wind_speed = float(panahon_obs.get("wind_speed") or curr.get("wind_speed_10m", 0.0))
        wind_dir = float(curr.get("wind_direction_10m", 0.0))
        pressure = float(panahon_obs.get("barometric_pressure_avg") or curr.get("pressure_msl", 1010.0))

        hi_c, hi_desc = _calculate_heat_index(air_temp, rh)
        cell_temp, derating_pct, pv_kw = _compute_pv(gti, air_temp, array_kwp, sys_eff)

        now_ph = datetime.now(PH_TZ)
        today_str = now_ph.strftime("%Y-%m-%d")
        tomorrow_str = (now_ph + timedelta(days=1)).strftime("%Y-%m-%d")

        h_times = hourly.get("time", [])
        h_gti = hourly.get("global_tilted_irradiance", [])
        h_temp = hourly.get("temperature_2m", [])

        today_kwh = 0.0
        tomorrow_kwh = 0.0
        today_psh = 0.0

        for idx, t_str in enumerate(h_times):
            g_poa = float(h_gti[idx]) if idx < len(h_gti) and h_gti[idx] is not None else 0.0
            t_amb = float(h_temp[idx]) if idx < len(h_temp) and h_temp[idx] is not None else 28.0
            _, _, step_kw = _compute_pv(g_poa, t_amb, array_kwp, sys_eff)
            if t_str.startswith(today_str):
                today_kwh += step_kw
                today_psh += g_poa / 1000.0
            elif t_str.startswith(tomorrow_str):
                tomorrow_kwh += step_kw

        d_rain = daily.get("precipitation_sum", [0.0])
        d_wind = daily.get("wind_speed_10m_max", [wind_speed])
        today_rain_mm = float(d_rain[0]) if d_rain else 0.0
        max_wind_today = float(d_wind[0]) if d_wind else wind_speed

        if max_wind_today >= 62.0 or precip_1h >= 15.0 or today_rain_mm >= 50.0:
            advisory = "Severe Weather / Typhoon Watch - Charge Battery to 100% Grid Backup"
        elif tomorrow_kwh < (array_kwp * 2.2) or today_rain_mm >= 15.0 or cloud_cover >= 85.0:
            advisory = "High Cloud / Monsoon Rain Expected - Hold 50% Battery Reserve"
        elif pv_kw >= (array_kwp * 0.55):
            advisory = "Peak Solar Production - Run High-Load Appliances / AC Precooling"
        else:
            advisory = "Normal Solar Self-Consumption"

        return {
            "air_temperature_avg": round(air_temp, 1),
            "relative_humidity_avg": round(rh, 1),
            "heat_index_avg": hi_c,
            "heat_index_description": hi_desc,
            "solar_radiation_avg": round(ghi, 1),
            "global_tilted_irradiance": round(gti, 1),
            "pv_cell_temp_c": cell_temp,
            "thermal_derating_pct": derating_pct,
            "estimated_pv_power_kw": pv_kw,
            "estimated_today_pv_kwh": round(today_kwh, 2),
            "estimated_tomorrow_pv_kwh": round(tomorrow_kwh, 2),
            "peak_sun_hours_today": round(today_psh, 2),
            "rainfall_1h_mm": round(precip_1h, 2),
            "today_rain_mm": round(today_rain_mm, 2),
            "cloud_cover_pct": round(cloud_cover, 1),
            "wind_speed_kmh": round(wind_speed, 1),
            "wind_direction_deg": round(wind_dir, 0),
            "barometric_pressure_hpa": round(pressure, 1),
            "weather_code": int(curr.get("weather_code", 1)),
            "typhoon_battery_advisory": advisory,
            "daily": daily,
        }
