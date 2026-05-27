"""RSPro RS510 Modbus RTU integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_BAUDRATE,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ADDRESS,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)
from .modbus_client import RS510ModbusClient, RS510Status

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["fan", "number", "sensor", "switch"]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up RS510 from a config entry."""
    client = RS510ModbusClient(
        port=entry.data[CONF_SERIAL_PORT],
        baudrate=entry.data[CONF_BAUDRATE],
        slave_address=entry.data[CONF_SLAVE_ADDRESS],
    )

    if not await client.async_connect():
        raise ConfigEntryNotReady(
            f"RS510: Keine Verbindung zu {entry.data[CONF_SERIAL_PORT]}"
        )

    poll_interval = entry.data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL)

    coordinator = RS510DataUpdateCoordinator(
        hass,
        client=client,
        update_interval=timedelta(seconds=poll_interval),
        entry_id=entry.entry_id,
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        data = hass.data[DOMAIN].pop(entry.entry_id)
        await data["client"].async_disconnect()
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


class RS510DataUpdateCoordinator(DataUpdateCoordinator[RS510Status]):
    """Polls the RS510 on a fixed interval.

    All entities (fan + sensors) share this coordinator so that only
    one Modbus read is issued per cycle.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        client: RS510ModbusClient,
        update_interval: timedelta,
        entry_id: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{entry_id}",
            update_interval=update_interval,
        )
        self.client = client

    async def _async_update_data(self) -> RS510Status:
        status = await self.client.async_read_status()
        if status is None:
            raise UpdateFailed("RS510: Statusregister konnten nicht gelesen werden")
        return status
