"""Support for the Airzone Cloud sensors."""

from datetime import datetime
from typing import Any, Final, override

from aioairzone_cloud.const import (
    AZD_AIDOOS,
    AZD_AQ_INDEX,
    AZD_AQ_PM_1,
    AZD_AQ_PM_2P5,
    AZD_AQ_PM_10,
    AZD_CPU_USAGE,
    AZD_CURRENT,
    AZD_ENERGY_ACC,
    AZD_ENERGY_CLAMPS,
    AZD_ENERGY_PERIOD_END,
    AZD_ENERGY_RET,
    AZD_HUMIDITY,
    AZD_INDOOR_EXCHANGER_TEMP,
    AZD_INDOOR_RETURN_TEMP,
    AZD_INDOOR_WORK_TEMP,
    AZD_MEMORY_FREE,
    AZD_OUTDOOR_CONDENSER_PRESS,
    AZD_OUTDOOR_DISCHARGE_TEMP,
    AZD_OUTDOOR_ELECTRIC_CURRENT,
    AZD_OUTDOOR_EVAPORATOR_PRESS,
    AZD_OUTDOOR_EXCHANGER_TEMP,
    AZD_OUTDOOR_TEMP,
    AZD_POWER_TOTAL,
    AZD_TEMP,
    AZD_THERMOSTAT_BATTERY,
    AZD_THERMOSTAT_COVERAGE,
    AZD_VOLTAGE,
    AZD_WEBSERVERS,
    AZD_WIFI_RSSI,
    AZD_ZONES,
)

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfDensity,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfInformation,
    UnitOfPower,
    UnitOfPressure,
    UnitOfRatio,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .coordinator import AirzoneCloudConfigEntry, AirzoneUpdateCoordinator
from .entity import (
    AirzoneAidooEntity,
    AirzoneEnergyClampEntity,
    AirzoneEntity,
    AirzoneWebServerEntity,
    AirzoneZoneEntity,
)

ENERGY_CLAMP_SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        device_class=SensorDeviceClass.POWER,
        key=AZD_POWER_TOTAL,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # The API reports the energy of the last finished period, not a running
    # total, so these have no state class. See ENERGY_CLAMP_TOTAL_TYPES.
    SensorEntityDescription(
        device_class=SensorDeviceClass.ENERGY,
        key=AZD_ENERGY_ACC,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        translation_key="energy_consumed_last_hour",
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.ENERGY,
        entity_registry_enabled_default=False,
        key=AZD_ENERGY_RET,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        translation_key="energy_returned_last_hour",
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.CURRENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        key=AZD_CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.VOLTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        key=AZD_VOLTAGE,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

ENERGY_CLAMP_TOTAL_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        device_class=SensorDeviceClass.ENERGY,
        key=AZD_ENERGY_ACC,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="energy_total_consumed",
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.ENERGY,
        entity_registry_enabled_default=False,
        key=AZD_ENERGY_RET,
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        translation_key="energy_total_returned",
    ),
)

ATTR_LAST_PERIOD_END: Final = "last_period_end"


def accumulate_energy(
    total: float | None,
    last_end: datetime | None,
    energy: float | None,
    period_end: str | None,
) -> tuple[float | None, datetime | None]:
    """Add the energy of a finished period to a running total, once per period.

    The API only reports the last finished period (value + end timestamp), so
    the total is built by adding each new period when its end timestamp changes.
    """
    if energy is None or period_end is None:
        return total, last_end
    if (end := dt_util.parse_datetime(period_end)) is None:
        return total, last_end
    if last_end is not None and end <= last_end:
        return total, last_end

    if total is None:
        new_total = energy
    elif last_end is None:
        # Total restored without its period: use this one as baseline only.
        new_total = total
    else:
        new_total = total + energy
    return round(new_total, 3), end


AIDOO_SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_INDOOR_EXCHANGER_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="indoor_exchanger_temp",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_INDOOR_RETURN_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="indoor_return_temp",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_INDOOR_WORK_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="indoor_work_temp",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_CONDENSER_PRESS,
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_condenser_press",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_DISCHARGE_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_discharge_temp",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_ELECTRIC_CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_electric_current",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_EVAPORATOR_PRESS,
        native_unit_of_measurement=UnitOfPressure.KPA,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_evaporator_press",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_EXCHANGER_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_exchanger_temp",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_OUTDOOR_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="outdoor_temp",
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.TEMPERATURE,
        key=AZD_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

WEBSERVER_SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_CPU_USAGE,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="cpu_usage",
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_MEMORY_FREE,
        native_unit_of_measurement=UnitOfInformation.BYTES,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="free_memory",
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_WIFI_RSSI,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
    ),
)

ZONE_SENSOR_TYPES: Final[tuple[SensorEntityDescription, ...]] = (
    SensorEntityDescription(
        device_class=SensorDeviceClass.AQI,
        key=AZD_AQ_INDEX,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.PM1,
        key=AZD_AQ_PM_1,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.PM25,
        key=AZD_AQ_PM_2P5,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.PM10,
        key=AZD_AQ_PM_10,
        native_unit_of_measurement=UnitOfDensity.MICROGRAMS_PER_CUBIC_METER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.TEMPERATURE,
        key=AZD_TEMP,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.HUMIDITY,
        key=AZD_HUMIDITY,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        device_class=SensorDeviceClass.BATTERY,
        key=AZD_THERMOSTAT_BATTERY,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SensorEntityDescription(
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        key=AZD_THERMOSTAT_COVERAGE,
        native_unit_of_measurement=UnitOfRatio.PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        translation_key="thermostat_coverage",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: AirzoneCloudConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add Airzone Cloud sensors from a config_entry."""
    coordinator = entry.runtime_data

    # Aidoos
    sensors: list[AirzoneSensor] = [
        AirzoneAidooSensor(
            coordinator,
            description,
            aidoo_id,
            aidoo_data,
        )
        for aidoo_id, aidoo_data in coordinator.data.get(AZD_AIDOOS, {}).items()
        for description in AIDOO_SENSOR_TYPES
        if description.key in aidoo_data
    ]

    # Energy Clamps
    sensors.extend(
        AirzoneEnergyClampSensor(
            coordinator,
            description,
            clamp_id,
            clamp_data,
        )
        for clamp_id, clamp_data in coordinator.data.get(AZD_ENERGY_CLAMPS, {}).items()
        for description in ENERGY_CLAMP_SENSOR_TYPES
        if description.key in clamp_data
    )

    sensors.extend(
        AirzoneEnergyClampTotalSensor(
            coordinator,
            description,
            clamp_id,
            clamp_data,
        )
        for clamp_id, clamp_data in coordinator.data.get(AZD_ENERGY_CLAMPS, {}).items()
        for description in ENERGY_CLAMP_TOTAL_TYPES
        if description.key in clamp_data and AZD_ENERGY_PERIOD_END in clamp_data
    )

    # WebServers
    sensors.extend(
        AirzoneWebServerSensor(
            coordinator,
            description,
            ws_id,
            ws_data,
        )
        for ws_id, ws_data in coordinator.data.get(AZD_WEBSERVERS, {}).items()
        for description in WEBSERVER_SENSOR_TYPES
        if description.key in ws_data
    )

    # Zones
    sensors.extend(
        AirzoneZoneSensor(
            coordinator,
            description,
            zone_id,
            zone_data,
        )
        for zone_id, zone_data in coordinator.data.get(AZD_ZONES, {}).items()
        for description in ZONE_SENSOR_TYPES
        if description.key in zone_data
    )

    async_add_entities(sensors)


class AirzoneSensor(AirzoneEntity, SensorEntity):
    """Define an Airzone Cloud sensor."""

    @property
    @override
    def available(self) -> bool:
        """Return Airzone Cloud sensor availability."""
        return super().available and self.native_value is not None

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Update attributes when the coordinator updates."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Update sensor attributes."""
        self._attr_native_value = self.get_airzone_value(self.entity_description.key)


class AirzoneAidooSensor(AirzoneAidooEntity, AirzoneSensor):
    """Define an Airzone Cloud Aidoo sensor."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        description: SensorEntityDescription,
        aidoo_id: str,
        aidoo_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, aidoo_id, aidoo_data)

        self._attr_unique_id = f"{aidoo_id}_{description.key}"
        self.entity_description = description

        self._async_update_attrs()


class AirzoneEnergyClampSensor(AirzoneEnergyClampEntity, AirzoneSensor):
    """Define an Airzone Cloud Energy Clamp sensor."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        description: SensorEntityDescription,
        clamp_id: str,
        clamp_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, clamp_id, clamp_data)

        self._attr_unique_id = f"{clamp_id}_{description.key}"
        self.entity_description = description

        self._async_update_attrs()


class AirzoneEnergyClampTotalSensor(
    AirzoneEnergyClampEntity, AirzoneSensor, RestoreSensor
):
    """Define an Airzone Cloud Energy Clamp running total sensor."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        description: SensorEntityDescription,
        clamp_id: str,
        clamp_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, clamp_id, clamp_data)

        self._attr_unique_id = f"{clamp_id}_{description.key}_total"
        self.entity_description = description

        self._total: float | None = None
        self._last_period_end: datetime | None = None

    @override
    async def async_added_to_hass(self) -> None:
        """Restore the running total before handling the first update."""
        await super().async_added_to_hass()

        if (
            last_data := await self.async_get_last_sensor_data()
        ) is not None and last_data.native_value is not None:
            try:
                self._total = float(last_data.native_value)
            except (TypeError, ValueError):
                self._total = None
        if (last_state := await self.async_get_last_state()) is not None and (
            raw_end := last_state.attributes.get(ATTR_LAST_PERIOD_END)
        ):
            self._last_period_end = dt_util.parse_datetime(raw_end)

        self._async_update_attrs()

    @property
    @override
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the last period counted in the total."""
        if self._last_period_end is None:
            return None
        return {ATTR_LAST_PERIOD_END: self._last_period_end.isoformat()}

    @callback
    @override
    def _async_update_attrs(self) -> None:
        """Add a newly finished period to the total."""
        self._total, self._last_period_end = accumulate_energy(
            self._total,
            self._last_period_end,
            self.get_airzone_value(self.entity_description.key),
            self.get_airzone_value(AZD_ENERGY_PERIOD_END),
        )
        self._attr_native_value = self._total


class AirzoneWebServerSensor(AirzoneWebServerEntity, AirzoneSensor):
    """Define an Airzone Cloud WebServer sensor."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        description: SensorEntityDescription,
        ws_id: str,
        ws_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, ws_id, ws_data)

        self._attr_unique_id = f"{ws_id}_{description.key}"
        self.entity_description = description

        self._async_update_attrs()


class AirzoneZoneSensor(AirzoneZoneEntity, AirzoneSensor):
    """Define an Airzone Cloud Zone sensor."""

    def __init__(
        self,
        coordinator: AirzoneUpdateCoordinator,
        description: SensorEntityDescription,
        zone_id: str,
        zone_data: dict[str, Any],
    ) -> None:
        """Initialize."""
        super().__init__(coordinator, zone_id, zone_data)

        self._attr_unique_id = f"{zone_id}_{description.key}"
        self.entity_description = description

        self._async_update_attrs()
