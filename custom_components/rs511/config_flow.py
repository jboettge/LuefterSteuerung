"""Config flow for the RSPro RS511 integration."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BAUDRATE,
    CONF_MAX_FREQUENCY,
    CONF_MIN_FREQUENCY,
    CONF_POLL_INTERVAL,
    CONF_SERIAL_PORT,
    CONF_SLAVE_ADDRESS,
    DEFAULT_BAUDRATE,
    DEFAULT_MAX_FREQUENCY,
    DEFAULT_MIN_FREQUENCY,
    DEFAULT_POLL_INTERVAL,
    DEFAULT_SLAVE_ADDRESS,
    DOMAIN,
)
from .modbus_client import RS511ModbusClient

_BAUDRATES = [1200, 2400, 4800, 9600, 19200, 38400, 57600, 115200]

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SERIAL_PORT, default="/dev/ttyUSB0"): str,
        vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(_BAUDRATES),
        vol.Required(CONF_SLAVE_ADDRESS, default=DEFAULT_SLAVE_ADDRESS): vol.All(
            int, vol.Range(min=1, max=247)
        ),
        vol.Required(CONF_MIN_FREQUENCY, default=DEFAULT_MIN_FREQUENCY): vol.All(
            vol.Coerce(float), vol.Range(min=0.0, max=400.0)
        ),
        vol.Required(CONF_MAX_FREQUENCY, default=DEFAULT_MAX_FREQUENCY): vol.All(
            vol.Coerce(float), vol.Range(min=1.0, max=400.0)
        ),
        vol.Required(CONF_POLL_INTERVAL, default=DEFAULT_POLL_INTERVAL): vol.All(
            int, vol.Range(min=5, max=300)
        ),
    }
)


class RS511ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for RS511."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> FlowResult:
        """First (and only) config step: collect connection parameters."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if user_input[CONF_MIN_FREQUENCY] >= user_input[CONF_MAX_FREQUENCY]:
                errors["base"] = "freq_range_invalid"
            else:
                # Try to open the port and read one status register
                client = RS511ModbusClient(
                    port=user_input[CONF_SERIAL_PORT],
                    baudrate=user_input[CONF_BAUDRATE],
                    slave_address=user_input[CONF_SLAVE_ADDRESS],
                    timeout=3.0,
                )
                connected = await client.async_connect()
                if not connected:
                    errors["base"] = "cannot_connect"
                else:
                    status = await client.async_read_status()
                    await client.async_disconnect()
                    if status is None:
                        errors["base"] = "cannot_read"

            if not errors:
                unique_id = (
                    f"{user_input[CONF_SERIAL_PORT]}_"
                    f"{user_input[CONF_SLAVE_ADDRESS]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"RS511 ({user_input[CONF_SERIAL_PORT]})",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_SCHEMA,
            errors=errors,
            description_placeholders={
                "serial_port_hint": "/dev/ttyUSB0 oder /dev/ttyS0",
            },
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> RS511OptionsFlow:
        return RS511OptionsFlow(config_entry)


class RS511OptionsFlow(config_entries.OptionsFlow):
    """Options flow for adjusting poll interval and frequency limits."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(
        self, user_input: dict | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        data = self._entry.data

        if user_input is not None:
            if user_input[CONF_MIN_FREQUENCY] >= user_input[CONF_MAX_FREQUENCY]:
                errors["base"] = "freq_range_invalid"
            else:
                return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MIN_FREQUENCY,
                    default=data.get(CONF_MIN_FREQUENCY, DEFAULT_MIN_FREQUENCY),
                ): vol.All(vol.Coerce(float), vol.Range(min=0.0, max=400.0)),
                vol.Required(
                    CONF_MAX_FREQUENCY,
                    default=data.get(CONF_MAX_FREQUENCY, DEFAULT_MAX_FREQUENCY),
                ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=400.0)),
                vol.Required(
                    CONF_POLL_INTERVAL,
                    default=data.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                ): vol.All(int, vol.Range(min=5, max=300)),
            }
        )
        return self.async_show_form(
            step_id="init", data_schema=schema, errors=errors
        )
