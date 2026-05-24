"""Fan platform for the RSPro RS510 integration."""

from __future__ import annotations

import logging
import math
from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
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
    PRESET_FREQUENCY,
    PRESET_HIGH,
    PRESET_LOW,
    PRESET_MEDIUM,
)

_LOGGER = logging.getLogger(__name__)

_PRESET_MODES = [PRESET_LOW, PRESET_MEDIUM, PRESET_HIGH]


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    coordinator: RS510DataUpdateCoordinator = data["coordinator"]
    async_add_entities([RS510Fan(coordinator, entry)])


class RS510Fan(CoordinatorEntity[RS510DataUpdateCoordinator], FanEntity):
    """Fan entity that maps percentage 1–100 % linearly to min–max Hz."""

    _attr_has_entity_name = True
    _attr_name = None
    _attr_icon = "mdi:fan"
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
    )
    _attr_preset_modes = _PRESET_MODES
    _attr_speed_count = 100

    def __init__(
        self,
        coordinator: RS510DataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_fan"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="RSPro",
            model="RS510-2P7-SH1",
        )
        self._min_freq: float = entry.data.get(CONF_MIN_FREQUENCY, DEFAULT_MIN_FREQUENCY)
        self._max_freq: float = entry.data.get(CONF_MAX_FREQUENCY, DEFAULT_MAX_FREQUENCY)
        self._client = coordinator.client

        self._opt_percentage: int | None = None
        self._opt_preset: str | None = None
        self._opt_on: bool | None = None

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success and self._client.available

    @property
    def is_on(self) -> bool:
        if self._opt_on is not None:
            return self._opt_on
        if self.coordinator.data is None:
            return False
        return self.coordinator.data.is_running

    @property
    def percentage(self) -> int | None:
        if self._opt_percentage is not None:
            return self._opt_percentage
        if self.coordinator.data is None or not self.coordinator.data.is_running:
            return 0
        return self._freq_to_pct(self.coordinator.data.output_frequency_hz)

    @property
    def preset_mode(self) -> str | None:
        if self._opt_preset is not None:
            return self._opt_preset
        if self.coordinator.data is None or not self.coordinator.data.is_running:
            return None
        current_freq = self.coordinator.data.output_frequency_hz
        for name, freq in PRESET_FREQUENCY.items():
            if math.isclose(current_freq, freq, abs_tol=0.5):
                return name
        return None

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        if preset_mode is not None:
            await self._apply_preset(preset_mode)
        elif percentage is not None:
            await self._apply_percentage(percentage)
        else:
            await self._apply_preset(PRESET_MEDIUM)

    async def async_turn_off(self, **kwargs: Any) -> None:
        if await self._client.async_stop():
            self._opt_on = False
            self._opt_percentage = 0
            self._opt_preset = None
            self.async_write_ha_state()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._apply_percentage(percentage)

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self._apply_preset(preset_mode)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _apply_percentage(self, percentage: int) -> None:
        freq = self._pct_to_freq(percentage)
        ok = await self._client.async_set_frequency(freq)
        if ok and not self.is_on:
            ok = await self._client.async_run_forward()
        if ok:
            self._opt_percentage = percentage
            self._opt_preset = None
            self._opt_on = True
            self.async_write_ha_state()

    async def _apply_preset(self, preset_mode: str) -> None:
        freq = PRESET_FREQUENCY[preset_mode]
        ok = await self._client.async_set_frequency(freq)
        if ok and not self.is_on:
            ok = await self._client.async_run_forward()
        if ok:
            self._opt_percentage = self._freq_to_pct(freq)
            self._opt_preset = preset_mode
            self._opt_on = True
            self.async_write_ha_state()

    def _pct_to_freq(self, percentage: int) -> float:
        pct = max(0, min(100, percentage))
        return self._min_freq + (pct / 100.0) * (self._max_freq - self._min_freq)

    def _freq_to_pct(self, frequency_hz: float) -> int:
        if self._max_freq <= self._min_freq:
            return 100
        pct = (frequency_hz - self._min_freq) / (self._max_freq - self._min_freq) * 100
        return max(0, min(100, round(pct)))

    @callback
    def _handle_coordinator_update(self) -> None:
        self._opt_percentage = None
        self._opt_preset = None
        self._opt_on = None
        super()._handle_coordinator_update()
