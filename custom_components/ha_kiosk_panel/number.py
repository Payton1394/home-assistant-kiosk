"""Number entities: display brightness and screensaver timeout."""
from __future__ import annotations

from homeassistant.components import mqtt
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            KioskBrightnessNumber(hass, entry),
            KioskScreensaverTimeoutNumber(hass, entry),
        ]
    )


class _KioskNumber(KioskEntity, NumberEntity):
    _cmd_suffix: str
    _state_suffix: str
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(hass, entry, key, name)
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            try:
                self._attr_native_value = float(msg.payload)
            except (TypeError, ValueError):
                return
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic(self._state_suffix), state_received, qos=0
            )
        )

    async def async_set_native_value(self, value: float) -> None:
        await mqtt.async_publish(self.hass, self._topic(self._cmd_suffix), str(int(value)))


class KioskBrightnessNumber(_KioskNumber):
    _cmd_suffix = "brightness/set"
    _state_suffix = "brightness/state"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_icon = "mdi:brightness-6"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "brightness", "Brightness")


class KioskScreensaverTimeoutNumber(_KioskNumber):
    _cmd_suffix = "screensaver_timeout/set"
    _state_suffix = "screensaver_timeout/state"
    _attr_native_min_value = 10
    _attr_native_max_value = 3600
    _attr_native_step = 10
    _attr_native_unit_of_measurement = UnitOfTime.SECONDS
    _attr_icon = "mdi:timer-outline"
    _attr_mode = NumberMode.BOX

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "screensaver_timeout", "Screensaver Timeout")
