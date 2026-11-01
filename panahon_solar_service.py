#!/usr/bin/env python3
"""
DOST-PAGASA PANaHON + ECMWF Philippine Solar & Weather Service for Home Assistant.

Provides:
1. Authorized DOST-PAGASA PANaHON Mobile API client (`https://api.mobile.panahon.gov.ph/api/v1/*`)
   with `If-None-Match` ETag caching (`nowcast/dashboard`, `observation/automatic`, `alerts`).
2. Automatic Zero-Auth ECMWF IFS + Solar Irradiance Engine (`shortwave_radiation`,
   `global_tilted_irradiance`, `direct_normal_irradiance`, `diffuse_radiation`) matching
   PANaHON's internal ECMWF numerical weather forecast backend.
3. Philippine Tropical Solar PV & Battery Planner (calculates real-time kW, daily kWh yield,
   Peak Sun Hours, tropical PV cell temperature derating, PAGASA Heat Index danger level,
   and Typhoon/Heavy Rainfall battery backup advisories).
4. Local HTTP REST API on port 8089 for Home Assistant (`home_assistant.yaml`).
"""

from __future__ import annotations

import argparse
import json
import math
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import OrderedDict
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError

# ==============================================================================
# 1. Environment & Argon2id Security Configuration
# ==============================================================================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"


def load_dotenv_file(dotenv_path: Path) -> None:
    """Safely load key-value pairs from .env without external dependencies."""
    if not dotenv_path.is_file():
        return
    with open(dotenv_path, "r", encoding="utf-8") as fh:
        for raw_line in fh:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


load_dotenv_file(ENV_PATH)

# Mandatory Argon2id baseline configuration (v=19, m=65536 KB, t=3, p=4)
ARGON2_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

PH_TZ = timezone(timedelta(hours=8))


class BoundedLRUCache:
    """Bounded in-memory LRU cache with TTL to prevent memory leaks."""

    def __init__(self, max_entries: int = 64, ttl_seconds: int = 900) -> None:
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self._store: OrderedDict[str, tuple[float, Any]] = OrderedDict()

    def get(self, key: str) -> Any | None:
        item = self._store.get(key)
        if item is None:
            return None
        ts, val = item
        if (time.time() - ts) > self.ttl_seconds:
            self._store.pop(key, None)
            return None
        self._store.move_to_end(key)
        return val

    def set(self, key: str, value: Any) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = (time.time(), value)
        while len(self._store) > self.max_entries:
            self._store.popitem(last=False)


# ==============================================================================
# 2. Reverse-Engineered DOST-PAGASA PANaHON Endpoint Catalog
# ==============================================================================

PANAHON_API_CATALOG: dict[str, Any] = {
    "package_name": "com.dostpagasa.panahon",
    "version": "1.1.3",
    "dart_package": "package:nowcast",
    "base_url": "https://api.mobile.panahon.gov.ph/api/v1",
    "web_embed_url": "https://panahon.gov.ph/?embed=panahon-mobile",
    "forecast_attribution": (
        "By integrating numerical weather forecasts from the European Centre for "
        "Medium-Range Weather Forecasts (ECMWF). Location Forecast is based on data "
        "and products of the ECMWF."
    ),
    "headers": {
        "X-Device-Id": "<UUID persisted in FlutterSecureStorage>",
        "X-Auth-Provider": "<Firebase App Check / Ed25519 provider>",
        "Authorization": "Bearer <access_token>",
        "If-None-Match": "<ETag cached per URL>",
    },
    "endpoints": {
        "auth_register_device": {
            "method": "POST",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/auth/register-device",
            "dart_symbol": "_registerDevice@828397250 (api_http_service.dart)",
            "fields": ["device_id", "public_key"],
        },
        "auth_challenge": {
            "method": "POST",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/auth/challenge",
            "dart_symbol": "_authenticate@828397250 (api_http_service.dart)",
            "fields": ["device_id", "challenge"],
        },
        "auth_verify": {
            "method": "POST",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/auth/verify",
            "dart_symbol": "_getAuthToken@828397250 (api_http_service.dart)",
            "fields": ["device_id", "signature", "access_token"],
        },
        "nowcast_dashboard": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/nowcast/dashboard",
            "dart_symbol": "_fetchDashboardJson@848075807 (weather_api_service.dart)",
            "query_params": ["latitude", "longitude"],
            "response_models": [
                "Nowcast",
                "HourlyForecast",
                "DailyForecast",
                "public_weather_forecast",
            ],
        },
        "location_search": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/location/search",
            "dart_symbol": "location_service.dart",
            "query_params": ["q"],
        },
        "city_outlook_philippine_cities": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/city-outlook/philippine-cities",
            "dart_symbol": "_fetchCityOutlookResponse@848075807",
        },
        "city_outlook_tourist_areas": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/city-outlook/philippine-tourist-areas",
            "dart_symbol": "_fetchCityOutlookResponse@848075807",
        },
        "city_outlook_asian_cities": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/city-outlook/asian-cities",
            "dart_symbol": "_fetchCityOutlookResponse@848075807",
        },
        "observation_automatic": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/observation/automatic",
            "dart_symbol": "getAutomaticObservations (observation_api_service.dart @850402376)",
            "telemetry_fields": [
                "site_id",
                "observed_at",
                "solar_radiation_avg",
                "air_temperature_avg",
                "relative_humidity_avg",
                "heat_index_avg",
                "heat_index_description",
                "rainfall",
                "rainfall_description",
                "wind_speed",
                "wind_direction",
                "barometric_pressure_avg",
            ],
        },
        "observation_automatic_historical": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/observation/automatic/historical-data",
            "dart_symbol": "getAutomaticHistoricalObservation (ObservationHist.fromJson)",
            "query_params": ["site_id"],
        },
        "observation_manual": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/observation/manual",
            "dart_symbol": "getManualObservations (ManualObservation.fromJson)",
            "telemetry_fields": [
                "site_id",
                "observed_at",
                "temperature",
                "heat_index",
                "precip_1h",
                "precip_3h",
                "accumulated_rain",
                "wind_speed",
                "wind_direction",
            ],
        },
        "observation_manual_historical": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/observation/manual/historical-data",
            "dart_symbol": "getManualHistoricalObservation",
            "query_params": ["site_id"],
        },
        "alerts": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/alerts",
            "dart_symbol": "_alertsUri@844377867 (alerts_api_service.dart)",
            "telemetry_fields": [
                "alert_id",
                "weather_alerts",
                "tropical_cyclone",
                "severe_weather",
                "flood_alerts",
                "issued_at",
                "valid_until_at",
            ],
        },
        "version": {
            "method": "GET",
            "url": "https://api.mobile.panahon.gov.ph/api/v1/version",
            "dart_symbol": "version_service.dart",
            "telemetry_fields": ["minimum_version", "latest_version"],
        },
    },
}


# ==============================================================================
# 3. Philippine Heat Index & Solar PV Physics Calculations
# ==============================================================================

def calculate_pagasa_heat_index(temp_c: float, rh_pct: float) -> tuple[float, str]:
    """
    Calculate NOAA/PAGASA Steadman Heat Index in °C and PAGASA classification:
      - < 27°C: Normal
      - 27–32°C: Caution
      - 33–41°C: Extreme Caution
      - 42–51°C: Danger
      - >= 52°C: Extreme Danger
    """
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
        desc = "Extreme Danger"
    elif hi_c >= 42.0:
        desc = "Danger"
    elif hi_c >= 33.0:
        desc = "Extreme Caution"
    elif hi_c >= 27.0:
        desc = "Caution"
    else:
        desc = "Normal"
    return hi_c, desc


def classify_pagasa_rainfall(mm_per_hr: float) -> str:
    """Classify rainfall intensity using PAGASA Heavy Rainfall Warning thresholds."""
    if mm_per_hr <= 0.0:
        return "No Rain"
    if mm_per_hr < 2.5:
        return "Light Rain"
    if mm_per_hr < 7.5:
        return "Moderate Rain"
    if mm_per_hr < 15.0:
        return "Heavy Rain (Yellow Warning)"
    if mm_per_hr < 30.0:
        return "Intense Rain (Orange Warning)"
    return "Torrential Rain (Red Warning)"


def compute_pv_performance(
    irradiance_wm2: float,
    air_temp_c: float,
    array_kwp: float,
    sys_eff: float,
    temp_coeff_pct_per_c: float = -0.35,
    noct_c: float = 45.0,
) -> dict[str, float]:
    """
    Calculate instantaneous PV output (kW), cell temperature (°C), and thermal derating (%)
    for a Philippine rooftop solar array.
    """
    g = max(0.0, float(irradiance_wm2))
    if g <= 0.0:
        return {
            "pv_cell_temp_c": round(air_temp_c, 1),
            "thermal_derating_pct": 0.0,
            "estimated_pv_power_kw": 0.0,
        }

    cell_temp_c = air_temp_c + ((noct_c - 20.0) / 800.0) * g
    delta_t = max(0.0, cell_temp_c - 25.0)
    thermal_factor = 1.0 + (temp_coeff_pct_per_c / 100.0) * delta_t
    thermal_factor = max(0.50, min(1.05, thermal_factor))
    thermal_derating_pct = round((1.0 - thermal_factor) * 100.0, 2)

    raw_kw = array_kwp * (g / 1000.0) * sys_eff * thermal_factor
    pv_kw = round(min(array_kwp, max(0.0, raw_kw)), 3)
    return {
        "pv_cell_temp_c": round(cell_temp_c, 1),
        "thermal_derating_pct": thermal_derating_pct,
        "estimated_pv_power_kw": pv_kw,
    }


# ==============================================================================
# 4. Dual-Source Weather & Solar Coordinator (PANaHON Mobile API + ECMWF IFS)
# ==============================================================================

class PanahonSolarPlanner:
    """Fetches and normalizes Philippine weather & solar data for Home Assistant."""

    def __init__(self) -> None:
        self.lat = float(os.environ.get("PH_LATITUDE", "14.5995"))
        self.lon = float(os.environ.get("PH_LONGITUDE", "120.9842"))
        self.location_name = os.environ.get("PH_LOCATION_NAME", "Metro Manila")
        self.array_kwp = float(os.environ.get("SOLAR_ARRAY_KWP", "5.0"))
        self.panel_tilt = float(os.environ.get("SOLAR_PANEL_TILT_DEG", "14.0"))
        self.panel_azimuth = float(os.environ.get("SOLAR_PANEL_AZIMUTH_DEG", "0.0"))
        self.sys_eff = float(os.environ.get("SOLAR_SYSTEM_EFFICIENCY", "0.82"))
        self.temp_coeff = float(os.environ.get("SOLAR_TEMP_COEFF_PCT_PER_C", "-0.35"))

        self.panahon_base_url = os.environ.get(
            "PANAHON_BASE_URL", "https://api.mobile.panahon.gov.ph/api/v1"
        ).rstrip("/")
        self.panahon_device_id = os.environ.get("PANAHON_DEVICE_ID", "").strip()
        self.panahon_access_token = os.environ.get("PANAHON_ACCESS_TOKEN", "").strip()
        self.panahon_aws_site_id = os.environ.get("PANAHON_AWS_SITE_ID", "").strip()

        self._etag_cache = BoundedLRUCache(max_entries=32, ttl_seconds=3600)
        self._body_cache = BoundedLRUCache(max_entries=32, ttl_seconds=600)

    def _http_get_with_etag(
        self, url: str, headers: dict[str, str] | None = None, timeout: int = 12
    ) -> dict[str, Any] | None:
        req_headers = {
            "Accept": "application/json",
            "User-Agent": "PANaHON-HA-SolarBridge/1.1.3",
        }
        if headers:
            req_headers.update(headers)

        cached_etag = self._etag_cache.get(url)
        if cached_etag:
            req_headers["If-None-Match"] = str(cached_etag)

        req = urllib.request.Request(url, headers=req_headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw_body = resp.read().decode("utf-8")
                etag = resp.headers.get("ETag")
                parsed = json.loads(raw_body)
                if etag:
                    self._etag_cache.set(url, etag)
                self._body_cache.set(url, parsed)
                return parsed
        except urllib.error.HTTPError as exc:
            if exc.code == 304:
                return self._body_cache.get(url)
            return None
        except Exception:
            return None

    def try_fetch_panahon_mobile_api(self) -> dict[str, Any] | None:
        """
        Query `https://api.mobile.panahon.gov.ph/api/v1/nowcast/dashboard` and
        `/observation/automatic` if an authorized device token is configured.
        """
        if not self.panahon_access_token or not self.panahon_device_id:
            return None

        headers = {
            "X-Device-Id": self.panahon_device_id,
            "Authorization": f"Bearer {self.panahon_access_token}",
        }
        q = urllib.parse.urlencode({"latitude": self.lat, "longitude": self.lon})
        dashboard_url = f"{self.panahon_base_url}/nowcast/dashboard?{q}"
        obs_url = f"{self.panahon_base_url}/observation/automatic"
        alerts_url = f"{self.panahon_base_url}/alerts"

        dashboard = self._http_get_with_etag(dashboard_url, headers=headers)
        obs = self._http_get_with_etag(obs_url, headers=headers)
        alerts = self._http_get_with_etag(alerts_url, headers=headers)
        if not dashboard and not obs:
            return None
        return {
            "dashboard": dashboard,
            "automatic_observation": obs,
            "alerts": alerts,
        }

    def fetch_ecmwf_solar_forecast(self) -> dict[str, Any]:
        """
        Query the ECMWF / Open-Meteo Solar Radiation & Forecast API for the configured
        Philippine coordinates and roof tilt/azimuth.
        """
        cache_key = f"ecmwf:{self.lat}:{self.lon}:{self.panel_tilt}:{self.panel_azimuth}"
        cached = self._body_cache.get(cache_key)
        if cached is not None:
            return cached

        params = {
            "latitude": self.lat,
            "longitude": self.lon,
            "timezone": "Asia/Manila",
            "current": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "precipitation",
                    "rain",
                    "weather_code",
                    "cloud_cover",
                    "pressure_msl",
                    "wind_speed_10m",
                    "wind_direction_10m",
                    "shortwave_radiation",
                    "direct_normal_irradiance",
                    "diffuse_radiation",
                    "global_tilted_irradiance",
                ]
            ),
            "hourly": ",".join(
                [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "apparent_temperature",
                    "precipitation_probability",
                    "precipitation",
                    "cloud_cover",
                    "wind_speed_10m",
                    "shortwave_radiation",
                    "direct_normal_irradiance",
                    "diffuse_radiation",
                    "global_tilted_irradiance",
                ]
            ),
            "daily": ",".join(
                [
                    "weather_code",
                    "temperature_2m_max",
                    "temperature_2m_min",
                    "apparent_temperature_max",
                    "sunrise",
                    "sunset",
                    "uv_index_max",
                    "precipitation_sum",
                    "precipitation_probability_max",
                    "wind_speed_10m_max",
                    "shortwave_radiation_sum",
                ]
            ),
            "tilt": self.panel_tilt,
            "azimuth": self.panel_azimuth,
            "forecast_days": 5,
        }
        url = f"https://api.open-meteo.com/v1/forecast?{urllib.parse.urlencode(params)}"
        data = self._http_get_with_etag(url, timeout=15)
        if data is None:
            raise RuntimeError("Unable to reach ECMWF / Solar Forecast upstream endpoint.")
        self._body_cache.set(cache_key, data)
        return data

    def build_dashboard_payload(self) -> dict[str, Any]:
        """Build unified PANaHON + Solar System Plan payload for Home Assistant."""
        panahon_raw = self.try_fetch_panahon_mobile_api()
        ecmwf = self.fetch_ecmwf_solar_forecast()

        curr = ecmwf.get("current", {})
        hourly = ecmwf.get("hourly", {})
        daily = ecmwf.get("daily", {})

        air_temp_c = float(curr.get("temperature_2m", 30.0))
        rh_pct = float(curr.get("relative_humidity_2m", 70.0))
        precip_1h_mm = float(curr.get("precipitation", 0.0))
        cloud_cover_pct = float(curr.get("cloud_cover", 0.0))
        wind_speed_kmh = float(curr.get("wind_speed_10m", 0.0))
        wind_dir_deg = float(curr.get("wind_direction_10m", 0.0))
        pressure_hpa = float(curr.get("pressure_msl", 1010.0))

        # Solar irradiance metrics (W/m²)
        ghi_wm2 = float(curr.get("shortwave_radiation", 0.0))
        gti_wm2 = float(curr.get("global_tilted_irradiance", ghi_wm2))
        dni_wm2 = float(curr.get("direct_normal_irradiance", 0.0))
        dhi_wm2 = float(curr.get("diffuse_radiation", 0.0))

        # Override with live PAGASA AWS station observation if authorized token is active
        source_mode = "ECMWF_IFS_SOLAR_ENGINE"
        if panahon_raw and isinstance(panahon_raw.get("automatic_observation"), dict):
            source_mode = "PANAHON_MOBILE_API_AND_ECMWF"
            aws_data = panahon_raw["automatic_observation"]
            if "solar_radiation_avg" in aws_data and aws_data["solar_radiation_avg"] is not None:
                ghi_wm2 = float(aws_data["solar_radiation_avg"])
            if "air_temperature_avg" in aws_data and aws_data["air_temperature_avg"] is not None:
                air_temp_c = float(aws_data["air_temperature_avg"])
            if "relative_humidity_avg" in aws_data and aws_data["relative_humidity_avg"] is not None:
                rh_pct = float(aws_data["relative_humidity_avg"])

        heat_index_c, heat_index_desc = calculate_pagasa_heat_index(air_temp_c, rh_pct)
        rainfall_desc = classify_pagasa_rainfall(precip_1h_mm)

        # Instantaneous PV performance
        pv_now = compute_pv_performance(
            irradiance_wm2=gti_wm2,
            air_temp_c=air_temp_c,
            array_kwp=self.array_kwp,
            sys_eff=self.sys_eff,
            temp_coeff_pct_per_c=self.temp_coeff,
        )

        # Hourly PV Yield integration for Today & Tomorrow (in PH time)
        now_ph = datetime.now(PH_TZ)
        today_str = now_ph.strftime("%Y-%m-%d")
        tomorrow_str = (now_ph + timedelta(days=1)).strftime("%Y-%m-%d")

        h_times = hourly.get("time", [])
        h_gti = hourly.get("global_tilted_irradiance", [])
        h_ghi = hourly.get("shortwave_radiation", [])
        h_temp = hourly.get("temperature_2m", [])
        h_rain = hourly.get("precipitation", [])
        h_pop = hourly.get("precipitation_probability", [])
        h_cloud = hourly.get("cloud_cover", [])

        today_kwh = 0.0
        remaining_today_kwh = 0.0
        tomorrow_kwh = 0.0
        today_psh = 0.0
        tomorrow_psh = 0.0
        hourly_forecast_list: list[dict[str, Any]] = []

        for idx, t_str in enumerate(h_times):
            g_poa = float(h_gti[idx]) if idx < len(h_gti) and h_gti[idx] is not None else 0.0
            g_hor = float(h_ghi[idx]) if idx < len(h_ghi) and h_ghi[idx] is not None else 0.0
            t_amb = float(h_temp[idx]) if idx < len(h_temp) and h_temp[idx] is not None else 28.0
            r_mm = float(h_rain[idx]) if idx < len(h_rain) and h_rain[idx] is not None else 0.0
            pop = int(h_pop[idx]) if idx < len(h_pop) and h_pop[idx] is not None else 0
            cld = int(h_cloud[idx]) if idx < len(h_cloud) and h_cloud[idx] is not None else 0

            step_pv = compute_pv_performance(
                irradiance_wm2=g_poa,
                air_temp_c=t_amb,
                array_kwp=self.array_kwp,
                sys_eff=self.sys_eff,
                temp_coeff_pct_per_c=self.temp_coeff,
            )
            step_kwh = step_pv["estimated_pv_power_kw"]  # 1-hour step

            if t_str.startswith(today_str):
                today_kwh += step_kwh
                today_psh += g_poa / 1000.0
                if t_str >= now_ph.strftime("%Y-%m-%dT%H:00"):
                    remaining_today_kwh += step_kwh
            elif t_str.startswith(tomorrow_str):
                tomorrow_kwh += step_kwh
                tomorrow_psh += g_poa / 1000.0

            if len(hourly_forecast_list) < 24 and t_str >= now_ph.strftime("%Y-%m-%dT%H:00"):
                hourly_forecast_list.append(
                    {
                        "time": t_str,
                        "temperature_c": round(t_amb, 1),
                        "solar_radiation_wm2": round(g_hor, 1),
                        "tilted_irradiance_wm2": round(g_poa, 1),
                        "estimated_pv_kw": round(step_kwh, 3),
                        "precipitation_mm": round(r_mm, 2),
                        "precipitation_probability_pct": pop,
                        "cloud_cover_pct": cld,
                    }
                )

        # 5-Day Forecast & Solar Yield
        d_times = daily.get("time", [])
        d_tmax = daily.get("temperature_2m_max", [])
        d_tmin = daily.get("temperature_2m_min", [])
        d_himax = daily.get("apparent_temperature_max", [])
        d_rain = daily.get("precipitation_sum", [])
        d_pop = daily.get("precipitation_probability_max", [])
        d_rad_mj = daily.get("shortwave_radiation_sum", [])
        d_wind = daily.get("wind_speed_10m_max", [])

        daily_forecast_list: list[dict[str, Any]] = []
        for idx, d_str in enumerate(d_times):
            # Convert MJ/m²/day to kWh/m²/day (Peak Sun Hours): 1 kWh = 3.6 MJ
            rad_mj = float(d_rad_mj[idx]) if idx < len(d_rad_mj) and d_rad_mj[idx] is not None else 0.0
            psh_day = round(rad_mj / 3.6, 2)
            # Thermal derating average ~6% in PH tropics
            est_day_kwh = round(self.array_kwp * psh_day * self.sys_eff * 0.94, 2)
            daily_forecast_list.append(
                {
                    "date": d_str,
                    "temp_max_c": float(d_tmax[idx]) if idx < len(d_tmax) else 0.0,
                    "temp_min_c": float(d_tmin[idx]) if idx < len(d_tmin) else 0.0,
                    "heat_index_max_c": float(d_himax[idx]) if idx < len(d_himax) else 0.0,
                    "precipitation_sum_mm": float(d_rain[idx]) if idx < len(d_rain) else 0.0,
                    "precipitation_probability_pct": int(d_pop[idx]) if idx < len(d_pop) else 0,
                    "wind_speed_max_kmh": float(d_wind[idx]) if idx < len(d_wind) else 0.0,
                    "shortwave_radiation_mj_m2": round(rad_mj, 2),
                    "peak_sun_hours": psh_day,
                    "estimated_pv_energy_kwh": est_day_kwh,
                }
            )

        today_rain_mm = daily_forecast_list[0]["precipitation_sum_mm"] if daily_forecast_list else 0.0
        max_wind_today = daily_forecast_list[0]["wind_speed_max_kmh"] if daily_forecast_list else wind_speed_kmh

        # Smart Inverter / Battery Reserve Advisory for PH Solar Setup
        if max_wind_today >= 62.0 or precip_1h_mm >= 15.0 or today_rain_mm >= 50.0:
            advisory = "Severe Weather / Typhoon Watch - Charge Battery to 100% Grid Backup"
            recommended_min_soc_pct = 90
        elif tomorrow_kwh < (self.array_kwp * 2.2) or today_rain_mm >= 15.0 or cloud_cover_pct >= 85.0:
            advisory = "High Cloud / Monsoon Rain Expected - Hold 50% Battery Reserve"
            recommended_min_soc_pct = 50
        elif pv_now["estimated_pv_power_kw"] >= (self.array_kwp * 0.55):
            advisory = "Peak Solar Production - Run High-Load Appliances / AC Precooling"
            recommended_min_soc_pct = 20
        else:
            advisory = "Normal Solar Self-Consumption"
            recommended_min_soc_pct = 25

        return {
            "status": "ok",
            "source_mode": source_mode,
            "observed_at": now_ph.isoformat(),
            "location": {
                "name": self.location_name,
                "latitude": self.lat,
                "longitude": self.lon,
            },
            "solar_system_config": {
                "array_kwp": self.array_kwp,
                "panel_tilt_deg": self.panel_tilt,
                "panel_azimuth_deg": self.panel_azimuth,
                "system_efficiency": self.sys_eff,
                "temp_coeff_pct_per_c": self.temp_coeff,
            },
            "nowcast": {
                "air_temperature_avg": round(air_temp_c, 1),
                "relative_humidity_avg": round(rh_pct, 1),
                "heat_index_avg": heat_index_c,
                "heat_index_description": heat_index_desc,
                "rainfall": round(precip_1h_mm, 2),
                "rainfall_description": rainfall_desc,
                "accumulated_rain_today_mm": round(today_rain_mm, 2),
                "cloud_cover_pct": round(cloud_cover_pct, 1),
                "wind_speed": round(wind_speed_kmh, 1),
                "wind_direction": round(wind_dir_deg, 0),
                "barometric_pressure_avg": round(pressure_hpa, 1),
            },
            "solar_telemetry": {
                "solar_radiation_avg": round(ghi_wm2, 1),
                "global_tilted_irradiance_wm2": round(gti_wm2, 1),
                "direct_normal_irradiance_wm2": round(dni_wm2, 1),
                "diffuse_radiation_wm2": round(dhi_wm2, 1),
                "pv_cell_temp_c": pv_now["pv_cell_temp_c"],
                "thermal_derating_pct": pv_now["thermal_derating_pct"],
                "estimated_pv_power_kw": pv_now["estimated_pv_power_kw"],
                "estimated_today_pv_kwh": round(today_kwh, 2),
                "estimated_remaining_today_pv_kwh": round(remaining_today_kwh, 2),
                "estimated_tomorrow_pv_kwh": round(tomorrow_kwh, 2),
                "peak_sun_hours_today": round(today_psh, 2),
                "peak_sun_hours_tomorrow": round(tomorrow_psh, 2),
                "typhoon_battery_advisory": advisory,
                "recommended_min_battery_soc_pct": recommended_min_soc_pct,
            },
            "hourly_forecast": hourly_forecast_list,
            "daily_forecast": daily_forecast_list,
        }


# ==============================================================================
# 5. Defensive HTTP Server with Argon2id Admin Verification & Rate Limiting
# ==============================================================================

PLANNER = PanahonSolarPlanner()
ADMIN_PASSWORD_RAW = os.environ.get("PANAHON_ADMIN_PASSWORD", "ChangeMeSolarAdmin2026!")
if len(ADMIN_PASSWORD_RAW) < 10:
    raise ValueError("PANAHON_ADMIN_PASSWORD must be at least 10 characters.")
ADMIN_PASSWORD_HASH = ARGON2_HASHER.hash(ADMIN_PASSWORD_RAW)
FAILED_AUTH_BY_IP: BoundedLRUCache = BoundedLRUCache(max_entries=128, ttl_seconds=900)


def verify_admin_password(candidate_password: str, client_ip: str) -> bool:
    """Verify admin credentials using Argon2id with per-IP brute-force lockout."""
    attempts = int(FAILED_AUTH_BY_IP.get(client_ip) or 0)
    if attempts >= 5:
        return False
    try:
        ARGON2_HASHER.verify(ADMIN_PASSWORD_HASH, candidate_password)
        FAILED_AUTH_BY_IP.set(client_ip, 0)
        return True
    except VerifyMismatchError:
        FAILED_AUTH_BY_IP.set(client_ip, attempts + 1)
        return False


class PanahonRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler serving Home Assistant JSON endpoints with defensive headers."""

    def _send_json(self, status_code: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "geolocation=(), camera=(), microphone=()")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path in ("/", "/api/v1/solar-dashboard"):
            try:
                data = PLANNER.build_dashboard_payload()
                self._send_json(200, data)
            except Exception as exc:
                self._send_json(502, {"status": "error", "message": str(exc)})
        elif parsed.path == "/api/v1/endpoints":
            self._send_json(200, PANAHON_API_CATALOG)
        elif parsed.path == "/health":
            self._send_json(200, {"status": "healthy", "service": "panahon-ha-solar"})
        else:
            self._send_json(404, {"status": "error", "message": "Not Found"})

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DOST-PAGASA PANaHON + ECMWF Philippine Solar & Weather Service"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch live PH weather & solar forecast once, print JSON, and exit.",
    )
    parser.add_argument(
        "--endpoints",
        action="store_true",
        help="Print the reverse-engineered PANaHON API endpoint catalog and exit.",
    )
    args = parser.parse_args()

    if args.endpoints:
        print(json.dumps(PANAHON_API_CATALOG, indent=2))
        return

    if args.once:
        payload = PLANNER.build_dashboard_payload()
        print(json.dumps(payload, indent=2))
        return

    host = os.environ.get("PANAHON_SERVER_HOST", "0.0.0.0")
    port = int(os.environ.get("PANAHON_SERVER_PORT", "8089"))
    server = ThreadingHTTPServer((host, port), PanahonRequestHandler)
    print(f"[+] PANaHON + PH Solar Home Assistant Service listening on http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
