"""Constants for the Home Assistant Kiosk Panel integration."""

DOMAIN = "ha_kiosk_panel"

CONF_BASE_TOPIC = "base_topic"
CONF_HOST = "host"
CONF_MPD_PORT = "mpd_port"

DEFAULT_MPD_PORT = 6600
DEFAULT_BASE_TOPIC_PREFIX = "kiosk/"

# What the media player plays through (an option, set under Configure):
# MPD on the kiosk, or the kiosk's dashboard page in Chromium, reached over
# MQTT through the Scarth Wall Panel add-on (<base>/media/set, /media/state).
CONF_AUDIO = "audio"
AUDIO_MPD = "mpd"
AUDIO_BROWSER = "browser"
DEFAULT_AUDIO = AUDIO_MPD

MANUFACTURER = "Home Assistant Kiosk"
MODEL = "Kiosk Panel"

# Discovery / identity. Published retained by kiosk_config_mqtt.py on the
# device (see build/scripts/kiosk_config_mqtt.py in the ha-kiosk-panel repo).
DISCOVERY_TOPIC = "kiosk/+/panel/state"


def topic(base_topic: str, suffix: str) -> str:
    """Build a full MQTT topic from a kiosk's base_topic + suffix."""
    return f"{base_topic.rstrip('/')}/{suffix}"
