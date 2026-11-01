"""Constants for DOST-PAGASA PANaHON & PH Solar Forecast integration."""

DOMAIN = "panahon_solar"
DEFAULT_NAME = "PANaHON PH Solar"
DEFAULT_LATITUDE = 14.5995
DEFAULT_LONGITUDE = 120.9842
DEFAULT_ARRAY_KWP = 5.0
DEFAULT_PANEL_TILT = 14.0
DEFAULT_PANEL_AZIMUTH = 0.0
DEFAULT_SYS_EFFICIENCY = 0.82

CONF_ARRAY_KWP = "array_kwp"
CONF_PANEL_TILT = "panel_tilt"
CONF_PANEL_AZIMUTH = "panel_azimuth"
CONF_SYS_EFFICIENCY = "system_efficiency"
CONF_DEVICE_ID = "panahon_device_id"
CONF_ACCESS_TOKEN = "panahon_access_token"

PANAHON_BASE_URL = "https://api.mobile.panahon.gov.ph/api/v1"
