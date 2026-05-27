"""Switch platform for the RSPro RS510 integration (run / stop)."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import RS510DataUpdateCoordinator
from .const import DOMAIN

import logging
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RS510DataUpdateCoordinator = data["coordinator"]
    async_add_entities([RS510Switch(coordinator, entry)])


class RS510Switch(CoordinatorEntity[RS510DataUpdateCoordinator], SwitchEntity):
    """On/Off switch that starts or stops the inverter motor.

    Does not change the frequency setpoint — the motor restarts at whatever
    frequency was last written to REG_FREQ_SETPOINT (0x2502).
    """

    _attr_has_entity_name = True
    _attr_name = "Betrieb"
    _attr_icon = "mdi:power"
    _attr_translation_key = "run_switch"

    def __init__(
        self,
        coordinator: RS510DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_switch"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="RSPro",
            model="RS510-2P7-SH1",
        )
        self._client = coordinator.client
        self._optimistic_state: bool | None = None

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._client.available

    @property
    def is_on(self) -> bool:
        if self._optimistic_state is not None:
            return self._optimistic_state
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.is_running

    async def async_turn_on(self, **kwargs: Any) -> None:
        if await self._client.async_run_forward():
            self._optimistic_state = True
            self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self._client.async_stop():
            self._optimistic_state = False
            self.async_write_ha_state()

    @callback
    def _handle_coordinator_update(self) -> None:
        self._optimistic_state = None
        super()._handle_coordinator_update()
