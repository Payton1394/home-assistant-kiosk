"""Text entities: dashboard URL and screensaver URL, live-editable from HA."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            KioskDashboardUrlText(hass, entry),
            KioskScreensaverUrlText(hass, entry),
        ]
    )


class _KioskText(KioskEntity, TextEntity):
    _cmd_suffix: str
    _state_suffix: str
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(hass, entry, key, name)
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            self._attr_native_value = msg.payload
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic(self._state_suffix), state_received, qos=0
            )
        )

    async def async_set_value(self, value: str) -> None:
        await mqtt.async_publish(self.hass, self._topic(self._cmd_suffix), value)


class KioskDashboardUrlText(_KioskText):
    _cmd_suffix = "dashboard_url/set"
    _state_suffix = "dashboard_url/state"
    _attr_icon = "mdi:view-dashboard"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "dashboard_url", "Dashboard URL")


class KioskScreensaverUrlText(_KioskText):
    _cmd_suffix = "screensaver_url/set"
    _state_suffix = "screensaver_url/state"
    _attr_icon = "mdi:image-outline"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "screensaver_url", "Screensaver URL")
