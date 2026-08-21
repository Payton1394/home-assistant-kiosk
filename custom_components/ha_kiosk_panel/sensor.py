"""Sensor entities for a kiosk panel: CPU temperature, ambient lux, presence distance, software version."""
from __future__ import annotations

import json

from homeassistant.components import mqtt
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfLength, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import KioskEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            KioskCpuTempSensor(hass, entry),
            KioskLuxSensor(hass, entry),
            KioskPresenceDistanceSensor(hass, entry),
            KioskSoftwareVersionSensor(hass, entry),
        ]
    )


class _KioskStateTopicSensor(KioskEntity, SensorEntity):
    _state_suffix: str

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str) -> None:
        super().__init__(hass, entry, key, name)
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            self._attr_native_value = self._parse(msg.payload)
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic(self._state_suffix), state_received, qos=0
            )
        )

    def _parse(self, payload: str):
        try:
            return float(payload)
        except (TypeError, ValueError):
            return None


class KioskCpuTempSensor(_KioskStateTopicSensor):
    _state_suffix = "cpu_temp"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = True

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "cpu_temp", "CPU Temperature")


class KioskLuxSensor(_KioskStateTopicSensor):
    _state_suffix = "lux/state"
    _attr_device_class = SensorDeviceClass.ILLUMINANCE
    _attr_native_unit_of_measurement = "lx"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "lux", "Ambient Light")


class KioskPresenceDistanceSensor(_KioskStateTopicSensor):
    _state_suffix = "presence/distance"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.METERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_registry_enabled_default = False

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "presence_distance", "Presence Distance")


class KioskSoftwareVersionSensor(KioskEntity, SensorEntity):
    """Reads sw_version out of the panel/state identity payload - lets you
    see what kiosk_config_mqtt.py version a kiosk is running without SSHing
    in. panel/state is deliberately not retained (see kiosk_config_mqtt.py's
    publish_identity()), so this can take up to ~60s to populate after HA
    or the kiosk restarts - the next periodic re-announcement, not a bug."""

    _attr_icon = "mdi:tag-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "sw_version", "Software Version")
        self._attr_native_value = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            try:
                payload = json.loads(msg.payload)
            except (ValueError, TypeError):
                return
            version = payload.get("sw_version")
            if version:
                self._attr_native_value = version
                self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic("panel/state"), state_received, qos=0
            )
        )
