"""DataUpdateCoordinator for DOST-PAGASA PANaHON & PH Solar Forecast."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import re
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


def _clean_numeric(raw: Any, default: float = 0.0) -> float:
    """Parse numeric strings like '31 °C' or '0.34 mm' to float."""
    if raw is None:
        return default
    if isinstance(raw, (int, float)):
        return float(raw)
    cleaned = re.sub(r"[^\d.-]", "", str(raw)).strip()
    try:
        return float(cleaned) if cleaned else default
    except ValueError:
        return default


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
    """Coordinator fetching official DOST-PAGASA PANaHON data and solar irradiance."""

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

        panahon_dashboard: dict[str, Any] = {}
        panahon_alerts: list[dict[str, Any]] = []
        is_direct_panahon = False

        # 1. Fetch Official DOST-PAGASA PANaHON Nowcast Dashboard
        dashboard_url = f"{PANAHON_BASE_URL}/nowcast/dashboard?lat={lat}&lon={lon}"
        headers = {
            "Accept": "application/json",
            "User-Agent": "PANaHON/1.1.3 (DOST-PAGASA)",
        }
        if dashboard_url in self._etag_by_url:
            headers["If-None-Match"] = self._etag_by_url[dashboard_url]

        try:
            async with session.get(dashboard_url, headers=headers, timeout=12) as resp:
                if resp.status == 200:
                    raw_dash = await resp.json()
                    if raw_dash.get("success"):
                        panahon_dashboard = raw_dash
                        is_direct_panahon = True
                        etag = resp.headers.get("ETag")
                        if etag:
                            self._etag_by_url[dashboard_url] = etag
                            self._body_by_url[dashboard_url] = raw_dash
                elif resp.status == 304:
                    panahon_dashboard = self._body_by_url.get(dashboard_url, {})
                    is_direct_panahon = True
        except Exception as err:
            _LOGGER.debug("Direct PANaHON dashboard endpoint error: %s", err)

        # 2. Fetch Official DOST-PAGASA Weather & Typhoon Alerts
        alerts_url = f"{PANAHON_BASE_URL}/alerts"
        alerts_headers = {
            "Accept": "application/json",
            "User-Agent": "PANaHON/1.1.3 (DOST-PAGASA)",
        }
        if alerts_url in self._etag_by_url:
            alerts_headers["If-None-Match"] = self._etag_by_url[alerts_url]

        try:
            async with session.get(alerts_url, headers=alerts_headers, timeout=10) as resp:
                if resp.status == 200:
                    raw_alerts = await resp.json()
                    if raw_alerts.get("success"):
                        panahon_alerts = raw_alerts.get("data", [])
                        etag = resp.headers.get("ETag")
                        if etag:
                            self._etag_by_url[alerts_url] = etag
                            self._body_by_url[alerts_url] = raw_alerts
                elif resp.status == 304:
                    cached = self._body_by_url.get(alerts_url, {})
                    panahon_alerts = cached.get("data", [])
        except Exception as err:
            _LOGGER.debug("Direct PANaHON alerts endpoint error: %s", err)

        # 3. Fetch Solar Irradiance Engine (ECMWF IFS Global Tilted & Horizontal Irradiance)
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
                    raise UpdateFailed(f"Solar forecast engine error: HTTP {resp.status}")
                ecmwf = await resp.json()
        except Exception as err:
            raise UpdateFailed(f"Error communicating with solar forecast engine: {err}") from err

        curr = ecmwf.get("current", {})
        hourly = ecmwf.get("hourly", {})
        daily = ecmwf.get("daily", {})

        # Extract Official DOST-PAGASA Nowcast Data
        nc = panahon_dashboard.get("data", {}).get("nc", {})
        meta = panahon_dashboard.get("meta", {})

        if is_direct_panahon and nc:
            data_source = "DOST-PAGASA PANaHON API (api.mobile.panahon.gov.ph)"
            air_temp = _clean_numeric(nc.get("tmp"), curr.get("temperature_2m", 30.0))
            hi_c = _clean_numeric(nc.get("hindex"), curr.get("apparent_temperature", 35.0))
            hi_desc = str(nc.get("hindex_desc") or "Caution")
            precip_1h = _clean_numeric(nc.get("tprecip"), curr.get("precipitation", 0.0))
            precip_desc = str(nc.get("tprecip_desc") or "No Rain")
            weather_desc = str(nc.get("desc") or "Partly cloudy")
        else:
            data_source = "ECMWF Numerical Tropical Forecast Engine"
            air_temp = float(curr.get("temperature_2m", 30.0))
            rh = float(curr.get("relative_humidity_2m", 70.0))
            hi_c, hi_desc = _calculate_heat_index(air_temp, rh)
            precip_1h = float(curr.get("precipitation", 0.0))
            precip_desc = "Rain" if precip_1h > 0 else "No Rain"
            weather_desc = "Partly Cloudy"

        rh = float(curr.get("relative_humidity_2m", 70.0))
        ghi = float(curr.get("shortwave_radiation", 0.0))
        gti = float(curr.get("global_tilted_irradiance", ghi))
        cloud_cover = float(curr.get("cloud_cover", 0.0))
        wind_speed = float(curr.get("wind_speed_10m", 0.0))
        wind_dir = float(curr.get("wind_direction_10m", 0.0))
        pressure = float(curr.get("pressure_msl", 1010.0))

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

        # Evaluate Active DOST-PAGASA Tropical Cyclone / Severe Weather Bulletins
        active_cyclone = any(
            "tropical cyclone" in str(a.get("type", "")).lower()
            or "typhoon" in str(a.get("title", "")).lower()
            for a in panahon_alerts
        )
        active_thunderstorm = any(
            "thunderstorm advisory" in str(a.get("type", "")).lower()
            for a in panahon_alerts
        )

        if active_cyclone or max_wind_today >= 62.0 or precip_1h >= 15.0 or today_rain_mm >= 50.0:
            advisory = "DOST-PAGASA Storm / Typhoon Watch - Hold 90% Battery Reserve for Grid Outage"
        elif tomorrow_kwh < (array_kwp * 2.2) or today_rain_mm >= 15.0 or cloud_cover >= 85.0:
            advisory = "High Cloud / Monsoon Rain Expected - Hold 50% Battery Reserve"
        elif pv_kw >= (array_kwp * 0.55):
            advisory = "Peak Solar Production - Run High-Load Appliances / AC Precooling"
        else:
            advisory = "Normal Solar Self-Consumption"

        return {
            "data_source": data_source,
            "pagasa_barangay": meta.get("barangay", ""),
            "pagasa_municipality": meta.get("municipality", ""),
            "pagasa_province": meta.get("province", ""),
            "pagasa_rain_map_url": panahon_dashboard.get("data", {}).get("rain_map", {}).get("url", ""),
            "pagasa_public_weather_url": panahon_dashboard.get("data", {}).get("public_weather_forecast", {}).get("url", ""),
            "air_temperature_avg": round(air_temp, 1),
            "relative_humidity_avg": round(rh, 1),
            "heat_index_avg": hi_c,
            "heat_index_description": hi_desc,
            "weather_description": weather_desc,
            "rainfall_1h_mm": round(precip_1h, 2),
            "rainfall_description": precip_desc,
            "today_rain_mm": round(today_rain_mm, 2),
            "solar_radiation_avg": round(ghi, 1),
            "global_tilted_irradiance": round(gti, 1),
            "pv_cell_temp_c": cell_temp,
            "thermal_derating_pct": derating_pct,
            "estimated_pv_power_kw": pv_kw,
            "estimated_today_pv_kwh": round(today_kwh, 2),
            "estimated_tomorrow_pv_kwh": round(tomorrow_kwh, 2),
            "peak_sun_hours_today": round(today_psh, 2),
            "cloud_cover_pct": round(cloud_cover, 1),
            "wind_speed_kmh": round(wind_speed, 1),
            "wind_direction_deg": round(wind_dir, 0),
            "barometric_pressure_hpa": round(pressure, 1),
            "weather_code": int(curr.get("weather_code", 1)),
            "typhoon_battery_advisory": advisory,
            "active_cyclone_alert": active_cyclone,
            "active_thunderstorm_alert": active_thunderstorm,
            "alerts_count": len(panahon_alerts),
            "daily": daily,
        }
