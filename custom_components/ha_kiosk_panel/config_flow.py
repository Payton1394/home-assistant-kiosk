"""Config flow for Home Assistant Kiosk Panel.

Supports two ways to add a kiosk:
  - Auto-discovery: triggered when any kiosk publishes its retained identity
    payload to ``kiosk/<name>/panel/state`` (see manifest.json's "mqtt" key
    and build/scripts/kiosk_config_mqtt.py on the device).
  - Manual entry, for kiosks not reachable via MQTT discovery yet (e.g. the
    retained message hasn't landed, or a non-default topic prefix is used).
"""
from __future__ import annotations

import json
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.components import mqtt
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_BASE_TOPIC,
    CONF_HOST,
    CONF_MPD_PORT,
    DEFAULT_BASE_TOPIC_PREFIX,
    DEFAULT_MPD_PORT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class KioskPanelConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a single kiosk panel."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovered: dict[str, Any] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            base_topic = user_input[CONF_BASE_TOPIC].strip().strip("/")
            await self.async_set_unique_id(base_topic)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=user_input["name"].strip() or base_topic,
                data={
                    "base_topic": base_topic,
                    CONF_HOST: user_input[CONF_HOST].strip(),
                    CONF_MPD_PORT: user_input[CONF_MPD_PORT],
                },
            )

        schema = vol.Schema(
            {
                vol.Required("name"): str,
                vol.Required(CONF_BASE_TOPIC, default=DEFAULT_BASE_TOPIC_PREFIX): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_MPD_PORT, default=DEFAULT_MPD_PORT): int,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_mqtt(self, discovery_info: mqtt.MqttServiceInfo) -> FlowResult:
        """Handle a kiosk announcing itself via its retained panel/state topic."""
        base_topic = discovery_info.topic.rsplit("/panel/state", 1)[0]

        await self.async_set_unique_id(base_topic)
        self._abort_if_unique_id_configured()

        try:
            payload = json.loads(discovery_info.payload)
        except (ValueError, TypeError):
            _LOGGER.debug("Ignoring non-JSON panel/state payload on %s", discovery_info.topic)
            return self.async_abort(reason="invalid_discovery_info")

        name = payload.get("name") or base_topic.rsplit("/", 1)[-1]
        host = payload.get("ip", "")
        mpd_port = payload.get("mpd_port", DEFAULT_MPD_PORT)
        sw_version = payload.get("sw_version")

        self._discovered = {
            "base_topic": base_topic,
            "name": name,
            CONF_HOST: host,
            CONF_MPD_PORT: mpd_port,
            "sw_version": sw_version,
        }

        self.context["title_placeholders"] = {"name": name}
        return await self.async_step_discovery_confirm()

    async def async_step_discovery_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            data = dict(self._discovered)
            data[CONF_HOST] = user_input[CONF_HOST].strip()
            data[CONF_MPD_PORT] = user_input[CONF_MPD_PORT]
            name = user_input["name"].strip() or data["name"]
            return self.async_create_entry(title=name, data=data)

        schema = vol.Schema(
            {
                vol.Required("name", default=self._discovered["name"]): str,
                vol.Required(CONF_HOST, default=self._discovered[CONF_HOST]): str,
                vol.Required(
                    CONF_MPD_PORT, default=self._discovered[CONF_MPD_PORT]
                ): int,
            }
        )
        return self.async_show_form(
            step_id="discovery_confirm",
            data_schema=schema,
            description_placeholders={"name": self._discovered["name"]},
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> KioskPanelOptionsFlow:
        return KioskPanelOptionsFlow(config_entry)


class KioskPanelOptionsFlow(config_entries.OptionsFlow):
    """Lets host/MPD port be corrected later (e.g. after a DHCP lease change)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            new_data = dict(self._entry.data)
            new_data[CONF_HOST] = user_input[CONF_HOST].strip()
            new_data[CONF_MPD_PORT] = user_input[CONF_MPD_PORT]
            self.hass.config_entries.async_update_entry(self._entry, data=new_data)
            return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self._entry.data[CONF_HOST]): str,
                vol.Required(
                    CONF_MPD_PORT, default=self._entry.data[CONF_MPD_PORT]
                ): int,
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
