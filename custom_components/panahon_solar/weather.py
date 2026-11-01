"""Weather platform for DOST-PAGASA PANaHON & PH Solar Forecast."""

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
    """Set up PANaHON weather entity."""
    coordinator: PanahonSolarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PanahonWeatherEntity(coordinator, entry)])


class PanahonWeatherEntity(
    CoordinatorEntity[PanahonSolarDataUpdateCoordinator], WeatherEntity
):
    """Home Assistant Weather Entity for DOST-PAGASA PANaHON & PH Solar."""

    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_native_precipitation_unit = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_native_pressure_unit = UnitOfPressure.HPA
    _attr_native_wind_speed_unit = UnitOfSpeed.KILOMETERS_PER_HOUR
    _attr_supported_features = WeatherEntityFeature.FORECAST_DAILY
    _attr_attribution = (
        "DOST-PAGASA PANaHON & ECMWF Numerical Weather Prediction"
    )

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
    def native_pressure(self) -> float | None:
        return self.coordinator.data.get("barometric_pressure_hpa") if self.coordinator.data else None

    @property
    def native_wind_speed(self) -> float | None:
        return self.coordinator.data.get("wind_speed_kmh") if self.coordinator.data else None

    @property
    def wind_bearing(self) -> float | None:
        return self.coordinator.data.get("wind_direction_deg") if self.coordinator.data else None

    @property
    def cloud_coverage(self) -> float | None:
        return self.coordinator.data.get("cloud_cover_pct") if self.coordinator.data else None

    async def async_forecast_daily(self) -> list[Forecast] | None:
        if not self.coordinator.data:
            return None
        daily = self.coordinator.data.get("daily", {})
        times = daily.get("time", [])
        codes = daily.get("weather_code", [])
        tmax = daily.get("temperature_2m_max", [])
        tmin = daily.get("temperature_2m_min", [])
        rain = daily.get("precipitation_sum", [])
        pop = daily.get("precipitation_probability_max", [])
        wind = daily.get("wind_speed_10m_max", [])

        forecasts: list[Forecast] = []
        for idx, dt_str in enumerate(times):
            wmo = int(codes[idx]) if idx < len(codes) and codes[idx] is not None else 1
            forecasts.append(
                Forecast(
                    datetime=dt_str,
                    condition=WMO_TO_HA_CONDITION.get(wmo, "partlycloudy"),
                    native_temperature=float(tmax[idx]) if idx < len(tmax) else None,
                    native_templow=float(tmin[idx]) if idx < len(tmin) else None,
                    native_precipitation=float(rain[idx]) if idx < len(rain) else None,
                    precipitation_probability=int(pop[idx]) if idx < len(pop) else None,
                    native_wind_speed=float(wind[idx]) if idx < len(wind) else None,
                )
            )
        return forecasts
