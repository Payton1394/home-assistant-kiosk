"""Media player for a kiosk panel: MPD on the kiosk, or its dashboard page.

By default it is the kiosk's local MPD instance (see build/mpd.conf handling
in build-image.sh), reachable at the kiosk's own IP on port 6600, spoken to
directly over the MPD protocol - not through MQTT.

With the entry's "audio" option set to "browser" it is the kiosk's dashboard
page instead (Chromium, the Scarth Wall Panel add-on), for a kiosk without
MPD: commands go out on <base>/media/set, the add-on hands them to the page,
and the page's reports come back on <base>/media/state. Same entity either
way, so automations and dashboards don't change.
"""
from __future__ import annotations

import json
import logging

from mpd.asyncio import MPDClient

from homeassistant.components import media_source, mqtt
from homeassistant.components.media_player import (
    BrowseMedia,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
    async_process_play_media_url,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import AUDIO_BROWSER, CONF_AUDIO, CONF_HOST, CONF_MPD_PORT, DEFAULT_AUDIO
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


SUPPORT_BROWSER = (
    MediaPlayerEntityFeature.PAUSE
    | MediaPlayerEntityFeature.PLAY
    | MediaPlayerEntityFeature.PLAY_MEDIA
    | MediaPlayerEntityFeature.STOP
    | MediaPlayerEntityFeature.VOLUME_SET
    | MediaPlayerEntityFeature.VOLUME_MUTE
    | MediaPlayerEntityFeature.SEEK
    | MediaPlayerEntityFeature.BROWSE_MEDIA
)

_BROWSER_STATE_MAP = {
    "playing": MediaPlayerState.PLAYING,
    "paused": MediaPlayerState.PAUSED,
    "buffering": MediaPlayerState.BUFFERING,
    "idle": MediaPlayerState.IDLE,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    if entry.options.get(CONF_AUDIO, DEFAULT_AUDIO) == AUDIO_BROWSER:
        async_add_entities([KioskBrowserMediaPlayer(hass, entry)])
    else:
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


class KioskBrowserMediaPlayer(KioskEntity, MediaPlayerEntity):
    """The kiosk's dashboard page as its media player (the "browser" option).

    The Scarth Wall Panel add-on relays <base>/media/set to the kiosk's page,
    which plays in an <audio> element on the kiosk's own speaker, and publishes
    the page's reports on <base>/media/state (retained JSON: page, state,
    volume, muted, title, duration, position, at). `page` is false while no
    page for the kiosk is connected; the entity is unavailable then, and
    whenever the kiosk itself is offline.

    Its volume is the room's volume and its mute is the room's Do Not
    Disturb: both cover everything the panel plays, and the panel's own Sound
    control changes the same settings. play_media takes extra.alarm (plays
    through Do Not Disturb) and extra.volume (that sound's own level).
    """

    _attr_supported_features = SUPPORT_BROWSER
    _attr_icon = "mdi:music-box-multiple-outline"
    _attr_media_content_type = MediaType.MUSIC

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(hass, entry, "media_player", "Media Player")
        self._page = False
        self._attr_state = MediaPlayerState.IDLE

    @property
    def available(self) -> bool:
        return super().available and self._page

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()

        @callback
        def state_received(msg) -> None:
            try:
                data = json.loads(msg.payload)
            except (ValueError, TypeError):
                return
            if not isinstance(data, dict):
                return
            self._page = bool(data.get("page"))
            self._attr_state = _BROWSER_STATE_MAP.get(data.get("state"), MediaPlayerState.IDLE)
            volume = data.get("volume")
            self._attr_volume_level = float(volume) if isinstance(volume, (int, float)) else None
            self._attr_is_volume_muted = bool(data.get("muted"))
            self._attr_media_title = data.get("title") or None
            duration = data.get("duration")
            self._attr_media_duration = (
                int(duration) if isinstance(duration, (int, float)) and duration > 0 else None
            )
            position, at = data.get("position"), data.get("at")
            if isinstance(position, (int, float)):
                self._attr_media_position = float(position)
                self._attr_media_position_updated_at = (
                    dt_util.utc_from_timestamp(at / 1000) if isinstance(at, (int, float)) else dt_util.utcnow()
                )
            else:
                self._attr_media_position = None
                self._attr_media_position_updated_at = None
            self.async_write_ha_state()

        self.async_on_remove(
            await mqtt.async_subscribe(
                self.hass, self._topic("media/state"), state_received, qos=0
            )
        )

    async def _send(self, command: str, **data) -> None:
        await mqtt.async_publish(
            self.hass, self._topic("media/set"), json.dumps({"command": command, **data}), qos=1
        )

    async def async_play_media(self, media_type: MediaType | str, media_id: str, **kwargs) -> None:
        """Play a URL or a media-source item (a local file, TTS) on the kiosk.

        Home Assistant's own media stays a path (/media/local/..., /api/...):
        the add-on serves the media folder itself and fetches /api through the
        Supervisor, so nothing goes out through the external URL - which is what
        Home Assistant's URL helpers pick when it serves TLS itself, as here.
        """
        if media_source.is_media_source_id(media_id):
            play_item = await media_source.async_resolve_media(self.hass, media_id, self.entity_id)
            media_id = play_item.url
        media_id = async_process_play_media_url(self.hass, media_id, allow_relative_url=True)
        extra = kwargs.get("extra") or {}
        payload = {"url": media_id, "title": extra.get("title")}
        # extra.alarm: heard through the room's Do Not Disturb (at full volume
        # unless given one); extra.volume: this sound's own level, 0-1,
        # instead of the room's volume.
        if extra.get("alarm"):
            payload["alarm"] = True
        volume = extra.get("volume")
        if isinstance(volume, (int, float)) and not isinstance(volume, bool):
            payload["volume"] = max(0.0, min(1.0, float(volume)))
        await self._send("play", **payload)

    async def async_media_play(self) -> None:
        await self._send("resume")

    async def async_media_pause(self) -> None:
        await self._send("pause")

    async def async_media_stop(self) -> None:
        await self._send("stop")

    async def async_media_seek(self, position: float) -> None:
        await self._send("seek", position=position)

    async def async_set_volume_level(self, volume: float) -> None:
        await self._send("volume", level=volume)

    async def async_mute_volume(self, mute: bool) -> None:
        await self._send("mute", muted=mute)

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=lambda item: item.media_content_type.startswith("audio/"),
        )
