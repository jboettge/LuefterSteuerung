"""Number platform for the RSPro RS510 integration (frequency setpoint)."""

from __future__ import annotations

from homeassistant.components.number import NumberDeviceClass, NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfFrequency
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RS510DataUpdateCoordinator
from .const import (
    CONF_MAX_FREQUENCY,
    CONF_MIN_FREQUENCY,
    DEFAULT_MAX_FREQUENCY,
    DEFAULT_MIN_FREQUENCY,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RS510DataUpdateCoordinator = data["coordinator"]
    async_add_entities([RS510FrequencyNumber(coordinator, entry)])


class RS510FrequencyNumber(CoordinatorEntity[RS510DataUpdateCoordinator], NumberEntity):
    """Number entity to set the inverter output frequency in Hz.

    Setting a value writes to REG_FREQ_SETPOINT (0x2502) and starts the motor.
    The displayed value reflects the frequency command echo from REG_SET_FREQ
    (0x2523) while running, or 0 when stopped.
    """

    _attr_has_entity_name = True
    _attr_name = "Sollfrequenz"
    _attr_translation_key = "frequency_setpoint"
    _attr_device_class = NumberDeviceClass.FREQUENCY
    _attr_native_unit_of_measurement = UnitOfFrequency.HERTZ
    _attr_native_step = 0.5
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: RS510DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_frequency"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="RSPro",
            model="RS510-2P7-SH1",
        )
        self._attr_native_min_value = float(
            entry.data.get(CONF_MIN_FREQUENCY, DEFAULT_MIN_FREQUENCY)
        )
        self._attr_native_max_value = float(
            entry.data.get(CONF_MAX_FREQUENCY, DEFAULT_MAX_FREQUENCY)
        )
        self._client = coordinator.client
        self._optimistic_value: float | None = None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._client.available

    @property
    def native_value(self) -> float | None:
        if self._optimistic_value is not None:
            return self._optimistic_value
        if self.coordinator.data is None:
            return None
        # Use set_frequency_hz (command echo 0x2523) when running,
        # output_frequency_hz (0x2524) as fallback
        if self.coordinator.data.is_running:
            return round(self.coordinator.data.set_frequency_hz, 2)
        return round(self.coordinator.data.output_frequency_hz, 2)

    async def async_set_native_value(self, value: float) -> None:
        ok = await self._client.async_set_frequency(value)
        if ok:
            self._optimistic_value = round(value, 2)
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._optimistic_value = None
        super()._handle_coordinator_update()
