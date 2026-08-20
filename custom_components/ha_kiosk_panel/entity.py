"""Shared base entity for kiosk MQTT-backed entities."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, MANUFACTURER, MODEL, topic


class KioskEntity(Entity):
    """Base class that wires up device info and MQTT availability."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str) -> None:
        self.hass = hass
        self._entry = entry
        self._base_topic: str = entry.data["base_topic"]
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_name = name
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._base_topic)},
            name=entry.title,
            manufacturer=MANUFACTURER,
            model=MODEL,
            sw_version=entry.data.get("sw_version"),
        )

    def _topic(self, suffix: str) -> str:
        return topic(self._base_topic, suffix)

    async def async_added_to_hass(self) -> None:
        @callback
        def availability_received(msg) -> None:
            self._attr_available = msg.payload == "online"
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic("availability"), availability_received, qos=0
            )
        )
