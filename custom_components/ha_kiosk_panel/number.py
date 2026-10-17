"""Number entities: display brightness, screensaver timeout, and the C4001
presence sensor's settings.

The presence settings (0.4.0, 2026-10-17) come from the kiosk's own
c4001_presence_mqtt.py: it publishes what the sensor holds as JSON on
<base>/presence/tuning/state and says whether it can be tuned on
<base>/presence/tuning/available; a change goes to <base>/presence/tuning/<key>/set
and the script stops the sensor, writes it to its flash, reads it back and
starts it again (about three seconds).
"""
from __future__ import annotations

import json

from homeassistant.components import mqtt
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfLength, UnitOfTime
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
            *(KioskPresenceNumber(hass, entry, *t) for t in PRESENCE_TUNABLES),
        ]
    )


# The C4001's presence-mode settings: entity key, name, the script's JSON key,
# min, max, step, unit, icon. Ranges and meanings: DFRobot's C4001 manual.
PRESENCE_TUNABLES = [
    ("presence_detection_distance", "Presence detection distance", "max_range", 1.0, 12.0, 0.1, UnitOfLength.METERS, "mdi:signal-distance-variant"),
    ("presence_trigger_distance", "Presence trigger distance", "trig_range", 0.6, 12.0, 0.1, UnitOfLength.METERS, "mdi:ray-start-arrow"),
    ("presence_trigger_sensitivity", "Presence trigger sensitivity", "trig_sens", 0, 9, 1, None, "mdi:tune-vertical"),
    ("presence_hold_sensitivity", "Presence hold sensitivity", "hold_sens", 0, 9, 1, None, "mdi:tune-vertical-variant"),
    ("presence_confirmation_delay", "Presence confirmation delay", "confirm_delay", 0.0, 5.0, 0.05, UnitOfTime.SECONDS, "mdi:timer-sand"),
    ("presence_clear_after", "Presence clear after", "clear_delay", 1, 600, 1, UnitOfTime.SECONDS, "mdi:timer-off-outline"),
]


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


class KioskPresenceNumber(KioskEntity, NumberEntity):
    """One of the C4001's settings; available while the kiosk is online and its
    presence script says the sensor can be tuned."""

    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str, json_key: str,
                 lo: float, hi: float, step: float, unit: str | None, icon: str) -> None:
        super().__init__(hass, entry, key, name)
        self._json_key = json_key
        self._attr_native_min_value = lo
        self._attr_native_max_value = hi
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = unit
        self._attr_icon = icon
        self._attr_native_value = None
        self._tunable = False

    @property
    def available(self) -> bool:
        return self._attr_available and self._tunable and self._attr_native_value is not None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            try:
                value = json.loads(msg.payload).get(self._json_key)
                self._attr_native_value = None if value is None else float(value)
            except (TypeError, ValueError, AttributeError):
                return
            self.async_write_ha_state()

        @callback
        def tunable_received(msg) -> None:
            self._tunable = msg.payload == "online"
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(self.hass, self._topic("presence/tuning/state"), state_received, qos=1)
        )
        self.async_on_remove(
            await mqtt.async_subscribe(self.hass, self._topic("presence/tuning/available"), tunable_received, qos=1)
        )

    async def async_set_native_value(self, value: float) -> None:
        payload = str(int(round(value))) if float(self._attr_native_step).is_integer() else f"{value:g}"
        await mqtt.async_publish(self.hass, self._topic(f"presence/tuning/{self._json_key}/set"), payload, qos=1)
