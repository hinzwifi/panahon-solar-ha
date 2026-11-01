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
        t_f = temp_c * 1.8 + 32.0
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


def _compute_pv(g: float, t_air: float, kwp: float, eff: float) -> tuple[float, float, float]:
    g = max(0.0, float(g))
    if g <= 0.0:
        return round(t_air, 1), 0.0, 0.0
    t_cell = t_air + (25.0 / 800.0) * g
    delta = max(0.0, t_cell - 25.0)
    loss = max(0.50, min(1.05, 1.0 - 0.0035 * delta))
    derate = round((1.0 - loss) * 100.0, 2)
    p_kw = round(min(kwp, max(0.0, kwp * (g / 1000.0) * eff * loss)), 3)
    return round(t_cell, 1), derate, p_kw


class PanahonSolarDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
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

        dash_data: dict[str, Any] = {}
        alerts_data: list[dict[str, Any]] = []
        is_panahon = False

        dash_url = f"{PANAHON_BASE_URL}/nowcast/dashboard?lat={lat}&lon={lon}"
        headers = {"Accept": "application/json", "User-Agent": "PANaHON/1.1.3 (DOST-PAGASA)"}
        if dash_url in self._etag_by_url:
            headers["If-None-Match"] = self._etag_by_url[dash_url]

        try:
            async with session.get(dash_url, headers=headers, timeout=10) as r:
                if r.status == 200:
                    raw = await r.json()
                    if raw.get("success"):
                        dash_data = raw
                        is_panahon = True
                        if "ETag" in r.headers:
                            self._etag_by_url[dash_url] = r.headers["ETag"]
                            self._body_by_url[dash_url] = raw
                elif r.status == 304:
                    dash_data = self._body_by_url.get(dash_url, {})
                    is_panahon = True
        except Exception as err:
            _LOGGER.debug("PANaHON dashboard fetch error: %s", err)

        alerts_url = f"{PANAHON_BASE_URL}/alerts"
        alerts_h = {"Accept": "application/json", "User-Agent": "PANaHON/1.1.3 (DOST-PAGASA)"}
        if alerts_url in self._etag_by_url:
            alerts_h["If-None-Match"] = self._etag_by_url[alerts_url]

        try:
            async with session.get(alerts_url, headers=alerts_h, timeout=8) as r:
                if r.status == 200:
                    raw_a = await r.json()
                    if raw_a.get("success"):
                        alerts_data = raw_a.get("data", [])
                        if "ETag" in r.headers:
                            self._etag_by_url[alerts_url] = r.headers["ETag"]
                            self._body_by_url[alerts_url] = raw_a
                elif r.status == 304:
                    alerts_data = self._body_by_url.get(alerts_url, {}).get("data", [])
        except Exception as err:
            _LOGGER.debug("PANaHON alerts fetch error: %s", err)

        om_params = {
            "latitude": lat,
            "longitude": lon,
            "timezone": "Asia/Manila",
            "current": (
                "temperature_2m,relative_humidity_2m,apparent_temperature,"
                "precipitation,weather_code,cloud_cover,pressure_msl,"
                "wind_speed_10m,wind_direction_10m,shortwave_radiation,"
                "direct_normal_irradiance,diffuse_radiation,global_tilted_irradiance"
            ),
            "hourly": "temperature_2m,precipitation,precipitation_probability,cloud_cover,shortwave_radiation,global_tilted_irradiance",
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,shortwave_radiation_sum",
            "tilt": tilt,
            "azimuth": azimuth,
            "forecast_days": 5,
        }
        try:
            async with session.get("https://api.open-meteo.com/v1/forecast", params=om_params, timeout=12) as r:
                if r.status != 200:
                    raise UpdateFailed(f"Weather engine error: {r.status}")
                meteo = await r.json()
        except Exception as err:
            raise UpdateFailed(f"Failed to fetch forecast: {err}") from err

        curr = meteo.get("current", {})
        hourly = meteo.get("hourly", {})
        daily = meteo.get("daily", {})

        nc = dash_data.get("data", {}).get("nc", {})
        meta = dash_data.get("meta", {})

        if is_panahon and nc:
            source = "DOST-PAGASA PANaHON API (api.mobile.panahon.gov.ph)"
            temp = _clean_numeric(nc.get("tmp"), curr.get("temperature_2m", 30.0))
            hi = _clean_numeric(nc.get("hindex"), curr.get("apparent_temperature", 35.0))
            hi_text = str(nc.get("hindex_desc") or "Caution")
            rain_1h = _clean_numeric(nc.get("tprecip"), curr.get("precipitation", 0.0))
            rain_text = str(nc.get("tprecip_desc") or "No Rain")
            wx_text = str(nc.get("desc") or "Partly cloudy")
        else:
            source = "ECMWF Tropical Forecast Engine"
            temp = float(curr.get("temperature_2m", 30.0))
            rh = float(curr.get("relative_humidity_2m", 70.0))
            hi, hi_text = _calculate_heat_index(temp, rh)
            rain_1h = float(curr.get("precipitation", 0.0))
            rain_text = "Rain" if rain_1h > 0 else "No Rain"
            wx_text = "Partly Cloudy"

        loc_parts = [meta.get("barangay"), meta.get("municipality"), meta.get("province"), meta.get("region")]
        resolved_loc = ", ".join([str(p) for p in loc_parts if p]) or f"{lat}, {lon}"

        rh = float(curr.get("relative_humidity_2m", 70.0))
        ghi = float(curr.get("shortwave_radiation", 0.0))
        gti = float(curr.get("global_tilted_irradiance", ghi))
        clouds = float(curr.get("cloud_cover", 0.0))
        w_speed = float(curr.get("wind_speed_10m", 0.0))
        w_dir = float(curr.get("wind_direction_10m", 0.0))
        press = float(curr.get("pressure_msl", 1010.0))

        t_cell, derate, pv_kw = _compute_pv(gti, temp, array_kwp, sys_eff)

        now_ph = datetime.now(PH_TZ)
        today_s = now_ph.strftime("%Y-%m-%d")
        tom_s = (now_ph + timedelta(days=1)).strftime("%Y-%m-%d")

        times = hourly.get("time", [])
        h_gti = hourly.get("global_tilted_irradiance", [])
        h_temp = hourly.get("temperature_2m", [])

        kwh_today = 0.0
        kwh_tom = 0.0
        psh_today = 0.0

        for i, t in enumerate(times):
            g_val = float(h_gti[i]) if i < len(h_gti) and h_gti[i] is not None else 0.0
            t_val = float(h_temp[i]) if i < len(h_temp) and h_temp[i] is not None else 28.0
            _, _, step_kw = _compute_pv(g_val, t_val, array_kwp, sys_eff)
            if t.startswith(today_s):
                kwh_today += step_kw
                psh_today += g_val / 1000.0
            elif t.startswith(tom_s):
                kwh_tom += step_kw

        d_rain = daily.get("precipitation_sum", [0.0])
        d_wind = daily.get("wind_speed_10m_max", [w_speed])
        rain_today = float(d_rain[0]) if d_rain else 0.0
        wind_max = float(d_wind[0]) if d_wind else w_speed

        has_cyclone = any(
            "tropical cyclone" in str(a.get("type", "")).lower()
            or "typhoon" in str(a.get("title", "")).lower()
            for a in alerts_data
        )
        has_tstorm = any(
            "thunderstorm" in str(a.get("type", "")).lower()
            for a in alerts_data
        )

        if has_cyclone or wind_max >= 62.0 or rain_1h >= 15.0 or rain_today >= 50.0:
            advisory = "PAGASA Storm / Typhoon Watch - Keep 90% Battery Reserve"
        elif kwh_tom < (array_kwp * 2.2) or rain_today >= 15.0 or clouds >= 85.0:
            advisory = "High Cloud / Rain Expected - Hold 50% Battery Reserve"
        elif pv_kw >= (array_kwp * 0.55):
            advisory = "Peak Solar - Good Time to Run AC / Precooling"
        else:
            advisory = "Normal Solar Self-Consumption"

        return {
            "data_source": source,
            "resolved_location": resolved_loc,
            "pagasa_barangay": meta.get("barangay", ""),
            "pagasa_municipality": meta.get("municipality", ""),
            "pagasa_province": meta.get("province", ""),
            "pagasa_rain_map_url": dash_data.get("data", {}).get("rain_map", {}).get("url", ""),
            "pagasa_public_weather_url": dash_data.get("data", {}).get("public_weather_forecast", {}).get("url", ""),
            "air_temperature_avg": round(temp, 1),
            "relative_humidity_avg": round(rh, 1),
            "heat_index_avg": hi,
            "heat_index_description": hi_text,
            "weather_description": wx_text,
            "rainfall_1h_mm": round(rain_1h, 2),
            "rainfall_description": rain_text,
            "today_rain_mm": round(rain_today, 2),
            "solar_radiation_avg": round(ghi, 1),
            "global_tilted_irradiance": round(gti, 1),
            "pv_cell_temp_c": t_cell,
            "thermal_derating_pct": derate,
            "estimated_pv_power_kw": pv_kw,
            "estimated_today_pv_kwh": round(kwh_today, 2),
            "estimated_tomorrow_pv_kwh": round(kwh_tom, 2),
            "peak_sun_hours_today": round(psh_today, 2),
            "cloud_cover_pct": round(clouds, 1),
            "wind_speed_kmh": round(w_speed, 1),
            "wind_direction_deg": round(w_dir, 0),
            "barometric_pressure_hpa": round(press, 1),
            "weather_code": int(curr.get("weather_code", 1)),
            "typhoon_battery_advisory": advisory,
            "active_cyclone_alert": has_cyclone,
            "active_thunderstorm_alert": has_tstorm,
            "alerts_count": len(alerts_data),
            "daily": daily,
        }
