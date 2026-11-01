from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfEnergy,
    UnitOfIrradiance,
    UnitOfPower,
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


@dataclass(frozen=True)
class PanahonSensorDescription(SensorEntityDescription):
    value_key: str = ""


SENSORS: tuple[PanahonSensorDescription, ...] = (
    PanahonSensorDescription(
        key="resolved_location",
        name="PANaHON Resolved Location",
        value_key="resolved_location",
        icon="mdi:map-marker",
    ),
    PanahonSensorDescription(
        key="weather_description",
        name="PANaHON Weather Condition",
        value_key="weather_description",
        icon="mdi:weather-partly-cloudy",
    ),
    PanahonSensorDescription(
        key="solar_radiation_avg",
        name="PANaHON Solar Radiation (GHI)",
        value_key="solar_radiation_avg",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="global_tilted_irradiance",
        name="PANaHON Roof Tilted Irradiance (GTI)",
        value_key="global_tilted_irradiance",
        native_unit_of_measurement=UnitOfIrradiance.WATTS_PER_SQUARE_METER,
        device_class=SensorDeviceClass.IRRADIANCE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="estimated_pv_power_kw",
        name="PANaHON Estimated PV Power",
        value_key="estimated_pv_power_kw",
        native_unit_of_measurement=UnitOfPower.KILO_WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="estimated_today_pv_kwh",
        name="PANaHON Today Forecasted PV Energy",
        value_key="estimated_today_pv_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
    ),
    PanahonSensorDescription(
        key="estimated_tomorrow_pv_kwh",
        name="PANaHON Tomorrow Forecasted PV Energy",
        value_key="estimated_tomorrow_pv_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    PanahonSensorDescription(
        key="peak_sun_hours_today",
        name="PANaHON Peak Sun Hours Today",
        value_key="peak_sun_hours_today",
        native_unit_of_measurement="h",
        icon="mdi:weather-sunny",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="pv_cell_temp_c",
        name="PANaHON PV Cell Temperature",
        value_key="pv_cell_temp_c",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="thermal_derating_pct",
        name="PANaHON Tropical Thermal Derating",
        value_key="thermal_derating_pct",
        native_unit_of_measurement=PERCENTAGE,
        icon="mdi:thermometer-chevron-down",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="air_temperature_avg",
        name="PANaHON Air Temperature",
        value_key="air_temperature_avg",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="heat_index_avg",
        name="PANaHON PAGASA Heat Index",
        value_key="heat_index_avg",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="rainfall_1h_mm",
        name="PANaHON 1h Rainfall",
        value_key="rainfall_1h_mm",
        native_unit_of_measurement=UnitOfPrecipitationDepth.MILLIMETERS,
        device_class=SensorDeviceClass.PRECIPITATION,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="cloud_cover_pct",
        name="PANaHON Cloud Cover",
        value_key="cloud_cover_pct",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="wind_speed_kmh",
        name="PANaHON Wind Speed",
        value_key="wind_speed_kmh",
        native_unit_of_measurement=UnitOfSpeed.KILOMETERS_PER_HOUR,
        device_class=SensorDeviceClass.WIND_SPEED,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="barometric_pressure_hpa",
        name="PANaHON Barometric Pressure",
        value_key="barometric_pressure_hpa",
        native_unit_of_measurement=UnitOfPressure.HPA,
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    PanahonSensorDescription(
        key="typhoon_battery_advisory",
        name="PANaHON Solar & Typhoon Battery Advisory",
        value_key="typhoon_battery_advisory",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: PanahonSolarDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        PanahonSolarSensor(coordinator, entry, desc) for desc in SENSORS
    )


class PanahonSolarSensor(CoordinatorEntity[PanahonSolarDataUpdateCoordinator], SensorEntity):
    entity_description: PanahonSensorDescription

    def __init__(
        self,
        coordinator: PanahonSolarDataUpdateCoordinator,
        entry: ConfigEntry,
        description: PanahonSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get(self.entity_description.value_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        if not self.coordinator.data:
            return {}
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            "data_source": data.get("data_source"),
            "resolved_location": data.get("resolved_location"),
        }

        if self.entity_description.key == "heat_index_avg":
            attrs.update({
                "pagasa_danger_level": data.get("heat_index_description"),
                "weather_description": data.get("weather_description"),
            })
        elif self.entity_description.key == "air_temperature_avg":
            attrs.update({
                "weather_description": data.get("weather_description"),
            })
        elif self.entity_description.key == "typhoon_battery_advisory":
            attrs.update({
                "active_cyclone_alert": data.get("active_cyclone_alert"),
                "active_thunderstorm_alert": data.get("active_thunderstorm_alert"),
                "dost_pagasa_alerts_count": data.get("alerts_count"),
                "pagasa_rain_map_url": data.get("pagasa_rain_map_url"),
                "pagasa_public_weather_url": data.get("pagasa_public_weather_url"),
            })
        return attrs
