"""Switch entities: display power (DPMS) and screensaver active state."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            KioskDpmsSwitch(hass, entry),
            KioskScreensaverSwitch(hass, entry),
        ]
    )


class _KioskSwitch(KioskEntity, SwitchEntity):
    _cmd_suffix: str
    _state_suffix: str

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(hass, entry, key, name)
        self._attr_is_on = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            self._attr_is_on = msg.payload.upper() == "ON"
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic(self._state_suffix), state_received, qos=0
            )
        )

    async def async_turn_on(self, **kwargs) -> None:
        await mqtt.async_publish(self.hass, self._topic(self._cmd_suffix), "ON")

    async def async_turn_off(self, **kwargs) -> None:
        await mqtt.async_publish(self.hass, self._topic(self._cmd_suffix), "OFF")


class KioskDpmsSwitch(_KioskSwitch):
    _cmd_suffix = "dpms/set"
    _state_suffix = "dpms/state"
    _attr_icon = "mdi:monitor"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "dpms", "Display Power")


class KioskScreensaverSwitch(_KioskSwitch):
    _cmd_suffix = "screensaver/set"
    _state_suffix = "screensaver/state"
    _attr_icon = "mdi:image-multiple-outline"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "screensaver", "Screensaver Active")
