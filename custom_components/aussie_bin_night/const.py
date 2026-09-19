"""Constants for Aussie Bin Night."""

DOMAIN = "aussie_bin_night"

CONF_ADDRESS = "address"
CONF_BIN_TYPES = "bin_types"
CONF_KNOWN_BIN_TYPES = "known_bin_types"
CONF_COUNCIL_ID = "council_id"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_POSTCODE = "postcode"
CONF_STATE = "state"
CONF_STREET = "street"
CONF_SUBURB = "suburb"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_REMINDER_LEAD_TIME = "reminder_lead_time"

DEFAULT_UPDATE_INTERVAL_DAYS = 7
DEFAULT_REMINDER_LEAD_TIME_HOURS = 12
API_BASE_URL = "https://binnighttonight.com/api"
REQUEST_TIMEOUT_SECONDS = 15
STATIC_URL = f"/api/{DOMAIN}/static"
