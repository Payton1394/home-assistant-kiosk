"""MPD media player for a kiosk panel.

The kiosk image runs a local MPD instance (see build/mpd.conf handling in
build-image.sh) reachable over the network at the kiosk's own IP on port
6600 by default. This talks to it directly over the MPD protocol - it does
not go through MQTT.
"""
from __future__ import annotations

import logging

from mpd.asyncio import MPDClient

from homeassistant.components import media_source
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    RepeatMode,
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import CONF_HOST, CONF_MPD_PORT
from .entity import KioskEntity

_LOGGER = logging.getLogger(__name__)

SUPPORT_MPD = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.NEXT_TRACK
    | MediaPlayerEntityFeature.PREVIOUS_TRACK
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SHUFFLE_SET
    | MediaPlayerEntityFeature.REPEAT_SET
    | MediaPlayerEntityFeature.SEEK
)

_STATE_MAP = {
    "play": MediaPlayerState.PLAYING,
    "pause": MediaPlayerState.PAUSED,
    "stop": MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([KioskMpdMediaPlayer(hass, entry)])


class KioskMpdMediaPlayer(KioskEntity, MediaPlayerEntity):
    _attr_should_poll = True
    _attr_supported_features = SUPPORT_MPD
    _attr_icon = "mdi:music-box-multiple-outline"

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "media_player", "Media Player")
        self._host = entry.data[CONF_HOST]
        self._port = entry.data[CONF_MPD_PORT]
        self._client = MPDClient()
        self._connected = False
        self._muted_volume: int | None = None

    async def _ensure_connected(self) -> bool:
        if self._connected:
            return True
        try:
            await self._client.connect(self._host, self._port)
            self._connected = True
            return True
        except Exception as err:  # noqa: BLE001 - any connect failure means "not available yet"
            _LOGGER.debug("Could not connect to MPD at %s:%s: %s", self._host, self._port, err)
            self._connected = False
            return False

    async def _command(self, name: str, *args):
        """Run an MPD command, dropping the connection on failure so the
        next poll/command retries a fresh connect instead of reusing a
        socket the daemon may have already closed."""
        if not await self._ensure_connected():
            return None
        try:
            return await getattr(self._client, name)(*args)
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("MPD command %s failed: %s", name, err)
            self._connected = False
            return None

    async def async_update(self) -> None:
        status = await self._command("status")
        if status is None:
            self._attr_available = False
            return
        song = await self._command("currentsong") or {}

        self._attr_available = True
        self._attr_state = _STATE_MAP.get(status.get("state"), MediaPlayerState.IDLE)

        volume = status.get("volume")
        self._attr_volume_level = (
            int(volume) / 100 if volume and volume.lstrip("-").isdigit() and int(volume) >= 0 else None
        )
        self._attr_is_volume_muted = self._attr_volume_level == 0 if self._attr_volume_level is not None else None

        self._attr_media_title = song.get("title")
        self._attr_media_artist = song.get("artist")
        self._attr_media_album_name = song.get("album")

        duration = status.get("duration") or song.get("time")
        self._attr_media_duration = int(float(duration)) if duration else None
        elapsed = status.get("elapsed")
        self._attr_media_position = float(elapsed) if elapsed else None
        self._attr_media_position_updated_at = dt_util.utcnow() if elapsed else None

        self._attr_shuffle = status.get("random") == "1"
        repeat_on = status.get("repeat") == "1"
        single_on = status.get("single") == "1"
        if repeat_on and single_on:
            self._attr_repeat = RepeatMode.ONE
        elif repeat_on:
            self._attr_repeat = RepeatMode.ALL
        else:
            self._attr_repeat = RepeatMode.OFF

    async def async_media_play(self) -> None:
        await self._command("play")

    async def async_media_pause(self) -> None:
        await self._command("pause", 1)

    async def async_media_stop(self) -> None:
        await self._command("stop")

    async def async_media_next_track(self) -> None:
        await self._command("next")

    async def async_media_previous_track(self) -> None:
        await self._command("previous")

    async def async_media_seek(self, position: float) -> None:
        await self._command("seekcur", position)

    async def async_play_media(self, media_type: str, media_id: str, **kwargs) -> None:
        """Play a URL or a Home Assistant media-source item.

        MPD is a separate service on the kiosk's own network address, so a
        media-source item (e.g. a local file browsed from HA) has to be
        resolved to a fully-qualified URL MPD can fetch itself - MPD never
        sees the original media-source URI.
        """
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            media_id = play_item.url
        media_id = async_process_play_media_url(self.hass, media_id)

        await self._command("clear")
        await self._command("add", media_id)
        await self._command("play")

    async def async_set_volume_level(self, volume: float) -> None:
        await self._command("setvol", int(volume * 100))

    async def async_mute_volume(self, mute: bool) -> None:
        if mute:
            status = await self._command("status") or {}
            self._muted_volume = int(status.get("volume") or 0)
            await self._command("setvol", 0)
        else:
            await self._command("setvol", self._muted_volume or 20)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        await self._command("random", 1 if shuffle else 0)

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        if repeat == RepeatMode.OFF:
            await self._command("repeat", 0)
            await self._command("single", 0)
        elif repeat == RepeatMode.ALL:
            await self._command("repeat", 1)
            await self._command("single", 0)
        else:
            await self._command("repeat", 1)
            await self._command("single", 1)
