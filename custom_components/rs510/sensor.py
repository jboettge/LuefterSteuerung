"""Sensor platform for the RSPro RS510 integration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfFrequency,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RS510DataUpdateCoordinator
from .const import DOMAIN, FAULT_CODES
from .modbus_client import RS510Status


@dataclass(frozen=True, kw_only=True)
class RS510SensorDescription(SensorEntityDescription):
    value_fn: Callable[[RS510Status], float | int | str | None]


_SENSORS: tuple[RS510SensorDescription, ...] = (
    RS510SensorDescription(
        key="output_frequency",
        translation_key="output_frequency",
        name="Ausgangsfrequenz",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
        suggested_display_precision=2,
        value_fn=lambda s: round(s.output_frequency_hz, 2),
    ),
    RS510SensorDescription(
        key="set_frequency",
        translation_key="set_frequency",
        name="Sollfrequenz",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:sine-wave",
        entity_registry_enabled_default=False,
        suggested_display_precision=2,
        value_fn=lambda s: round(s.set_frequency_hz, 2),
    ),
    RS510SensorDescription(
        key="output_current",
        translation_key="output_current",
        name="Ausgangsstrom",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda s: round(s.output_current_a, 2),
    ),
    RS510SensorDescription(
        key="output_voltage",
        translation_key="output_voltage",
        name="Ausgangsspannung",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda s: round(s.output_voltage_v, 1),
    ),
    RS510SensorDescription(
        key="dc_bus_voltage",
        translation_key="dc_bus_voltage",
        name="Zwischenkreisspannung",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        suggested_display_precision=1,
        value_fn=lambda s: round(s.dc_voltage_v, 1),
    ),
    RS510SensorDescription(
        key="heatsink_temp",
        translation_key="heatsink_temp",
        name="Kühlkörpertemperatur",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda s: s.heatsink_temp_c,
    ),
    RS510SensorDescription(
        key="fault_code",
        translation_key="fault_code",
        name="Fehlercode",
        icon="mdi:alert-circle-outline",
        value_fn=lambda s: FAULT_CODES.get(s.fault_code, f"Fehler {s.fault_code}"),
    ),
    RS510SensorDescription(
        key="status",
        translation_key="status",
        name="Status",
        icon="mdi:information-outline",
        value_fn=lambda s: _status_string(s),
    ),
)


def _status_string(status: RS510Status) -> str:
    if status.has_fault:
        return "Fehler"
    if status.is_running:
        return "Rückwärts" if status.is_reverse else "Vorwärts"
    if status.is_ready:
        return "Bereit"
    return "Gestoppt"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RS510DataUpdateCoordinator = data["coordinator"]
    async_add_entities(
        RS510Sensor(coordinator, entry, desc) for desc in _SENSORS
    )


class RS510Sensor(CoordinatorEntity[RS510DataUpdateCoordinator], SensorEntity):
    entity_description: RS510SensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: RS510DataUpdateCoordinator,
        entry: ConfigEntry,
        description: RS510SensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="RSPro",
            model="RS510-2P7-SH1",
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> float | int | str | None:
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)
