"""Presence binary sensor.

The two presence sensor options in the kiosk fleet publish to different
topics depending which hardware a given kiosk has: the C4001 mmWave sensor
uses ``presence/state``, the RCWL-0516 radar uses ``presence`` directly.
Rather than require the user to know which one their kiosk has, this
entity subscribes to both - whichever is actually wired up is the one that
will ever publish.
"""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KioskPresenceBinarySensor(hass, entry)])


class KioskPresenceBinarySensor(KioskEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.OCCUPANCY

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "presence", "Presence")
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def presence_received(msg) -> None:
            self._attr_is_on = msg.payload == "ON"
            self.async_write_ha_state()

        for suffix in ("presence/state", "presence"):
            self.async_on_remove(
                await mqtt.async_subscribe(
                    self.hass, self._topic(suffix), presence_received, qos=0
                )
            )
