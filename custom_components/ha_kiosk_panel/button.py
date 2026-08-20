"""Reboot and refresh buttons."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KioskRebootButton(hass, entry), KioskRefreshButton(hass, entry)])


class KioskRebootButton(KioskEntity, ButtonEntity):
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "reboot", "Reboot")

    async def async_press(self) -> None:
        await mqtt.async_publish(self.hass, self._topic("reboot/set"), "REBOOT")


class KioskRefreshButton(KioskEntity, ButtonEntity):
    """Hard-reloads (Ctrl+F5) the active Chromium window - much faster than
    a reboot, useful when a dashboard is stuck or after editing it."""

    _attr_icon = "mdi:refresh"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "refresh", "Refresh Dashboard")

    async def async_press(self) -> None:
        await mqtt.async_publish(self.hass, self._topic("refresh/set"), "REFRESH")
