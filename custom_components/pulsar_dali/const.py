from homeassistant.const import Platform

DOMAIN = "pulsar_dali"
DEFAULT_URL = "http://local-pulsar-dali-control:8099"
CONF_URL = "url"
CONF_TOKEN = "token"
CONF_FINGERPRINT = "fingerprint"
CONF_SCAN_ON_SETUP = "scan_on_setup"
PLATFORMS = [Platform.LIGHT, Platform.SWITCH, Platform.NUMBER, Platform.BINARY_SENSOR, Platform.BUTTON, Platform.EVENT, Platform.SENSOR, Platform.SCENE]
