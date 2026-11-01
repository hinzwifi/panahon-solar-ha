from __future__ import annotations

from typing import Any

from homeassistant.components.weather import (
    Forecast,
    WeatherEntity,
    WeatherEntityFeature,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfPrecipitationDepth,
    UnitOfPressure,
    UnitOfSpeed,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import PanahonSolarDataUpdateCoordinator

WMO_TO_HA_CONDITION: dict[int, str] = {
    0: "sunny",
    1: "partlycloudy",
    2: "partlycloudy",
    3: "cloudy",
    45: "fog",
    48: "fog",
    51: "rainy",
    53: "rainy",
    55: "rainy",
    61: "rainy",
    63: "rainy",
    65: "pouring",
    80: "rainy",
    81: "pouring",
    82: "pouring",
    95: "lightning-rainy",
    96: "lightning-rainy",
    99: "lightning-rainy",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PanahonSolarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PanahonWeatherEntity(coordinator, entry)])


class PanahonWeatherEntity(CoordinatorEntity[PanahonSolarDataUpdateCoordinator], WeatherEntity):
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    _attr_attribution = "DOST-PAGASA PANaHON & ECMWF"

    def __init__(
        self,
        coordinator: PanahonSolarDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_name = "PANaHON PH Forecast"
        self._attr_unique_id = f"{entry.entry_id}_weather"

    @property
    def condition(self) -> str | None:
        if not self.coordinator.data:
            return None
        code = int(self.coordinator.data.get("weather_code", 1))
        return WMO_TO_HA_CONDITION.get(code, "partlycloudy")

    @property
    def native_temperature(self) -> float | None:
        return self.coordinator.data.get("air_temperature_avg") if self.coordinator.data else None

    @property
    def native_apparent_temperature(self) -> float | None:
        return self.coordinator.data.get("heat_index_avg") if self.coordinator.data else None

    @property
    def humidity(self) -> float | None:
        return self.coordinator.data.get("relative_humidity_avg") if self.coordinator.data else None

    @property
    def native_wind_speed(self) -> float | None:
        return self.coordinator.data.get("wind_speed_kmh") if self.coordinator.data else None

    @property
    def wind_bearing(self) -> float | str | None:
        return self.coordinator.data.get("wind_direction_deg") if self.coordinator.data else None

    @property
    def native_pressure(self) -> float | None:
        return self.coordinator.data.get("barometric_pressure_hpa") if self.coordinator.data else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        return {
            "resolved_location": self.coordinator.data.get("resolved_location"),
            "data_source": self.coordinator.data.get("data_source"),
            "pagasa_weather_description": self.coordinator.data.get("weather_description"),
            "heat_index_description": self.coordinator.data.get("heat_index_description"),
            "active_cyclone_alert": self.coordinator.data.get("active_cyclone_alert"),
            "active_thunderstorm_alert": self.coordinator.data.get("active_thunderstorm_alert"),
            "today_rain_mm": self.coordinator.data.get("today_rain_mm"),
        }

    async def async_forecast_daily(self) -> list[Forecast] | None:
        if not self.coordinator.data:
            return None
        daily = self.coordinator.data.get("daily", {})
        times = daily.get("time", [])
        w_codes = daily.get("weather_code", [])
        t_max = daily.get("temperature_2m_max", [])
        t_min = daily.get("temperature_2m_min", [])
        precip = daily.get("precipitation_sum", [])
        prob = daily.get("precipitation_probability_max", [])
        wind = daily.get("wind_speed_10m_max", [])

        forecasts: list[Forecast] = []
        for i in range(len(times)):
            c_code = int(w_codes[i]) if i < len(w_codes) and w_codes[i] is not None else 1
            f: Forecast = {
                "datetime": times[i],
                "condition": WMO_TO_HA_CONDITION.get(c_code, "partlycloudy"),
                "native_temperature": float(t_max[i]) if i < len(t_max) and t_max[i] is not None else None,
                "native_templow": float(t_min[i]) if i < len(t_min) and t_min[i] is not None else None,
                "native_precipitation": float(precip[i]) if i < len(precip) and precip[i] is not None else 0.0,
                "precipitation_probability": int(prob[i]) if i < len(prob) and prob[i] is not None else 0,
                "native_wind_speed": float(wind[i]) if i < len(wind) and wind[i] is not None else 0.0,
            }
            forecasts.append(f)
        return forecasts
