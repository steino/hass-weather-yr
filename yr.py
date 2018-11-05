from datetime import datetime, timedelta
import logging
import requests
import xml.etree.ElementTree as ET

from requests.exceptions import (
        ConnectionError as ConnectError, HTTPError, Timeout)
import voluptuous as vol

from homeassistant.components.weather import (
        ATTR_FORECAST_TEMP, ATTR_FORECAST_TIME, ATTR_FORECAST_CONDITION,
        ATTR_FORECAST_WIND_SPEED, ATTR_FORECAST_WIND_BEARING,
        ATTR_FORECAST_TEMP_LOW, ATTR_FORECAST_PRECIPITATION,
        PLATFORM_SCHEMA, WeatherEntity)

from homeassistant.const import (
        CONF_API_KEY, CONF_LATITUDE, CONF_LONGITUDE, CONF_NAME, TEMP_CELSIUS,
        CONF_MODE, TEMP_FAHRENHEIT)
import homeassistant.helpers.config_validation as cv
from homeassistant.util import Throttle

import homeassistant.util.dt as dt_util

_LOGGER = logging.getLogger(__name__)

ATTRIBUTION = "Weather forecast from met.no, delivered by the Norwegian Meteorological Institute."
# https://api.met.no/license_data.html

MAP_CONDITION = {
        '1': 'sunny',
        '2': 'partlycloudy',
        '3': 'partlycloudy',
        '4': 'cloudy',
        '5': 'rainy',
        '6': 'rainy',
        '7': 'snowy-rainy',
        '8': 'snowy',
        '9': 'rainy',
        '10': 'pouring',
        '11': 'lightning-rainy',
        '12': 'snowy-rainy',
        '13': 'snowy',
        '15': 'fog',
        '22': 'lightning-rainy',
        '25': 'lightning-rainy',
        '30': 'lightning-rainy',
        '40': 'rainy',
        '41': 'rainy',
        '46': 'rainy',
        '47': 'snowy-rainy',
        '48': 'snowy-rainy',
        '49': 'snowy',
        '50': 'snowy',
}

#https://api.met.no/weatherapi/weathericon/1.1/documentation

DEFAULT_NAME = 'YR'

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Optional(CONF_LATITUDE): cv.latitude,
    vol.Optional(CONF_LONGITUDE): cv.longitude,
    vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string
})

MIN_TIME_BETWEEN_UPDATES = timedelta(minutes=3)

def setup_platform(hass, config, add_entities, discovery_info=None):
    """Set up the YR Weather. """
    latitude = config.get(CONF_LATITUDE, hass.config.latitude)
    longitude = config.get(CONF_LONGITUDE, hass.config.longitude)
    name = config.get(CONF_NAME)
    yr = YrData(latitude, longitude)

    add_entities([YrWeather(name, yr)], True)

class YrWeather(WeatherEntity):
    """Representation of a weather condition."""

    def __init__(self, name, yr):
        """Initialize YR weather."""
        self._name = name
        self._yr = yr

        self._ds_root = None
        self._ds_data = None
        self._ds_currently = None

    @property
    def attribution(self):
        """Return the attribution."""
        return ATTRIBUTION

    @property
    def name(self):
        """Return the name of the sensor."""
        return self._name

    @property
    def temperature(self):
        """Return the temperature."""
        return float(self._ds_currently.find("location/temperature").get("value"))

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def humidity(self):
        """Return the humidity."""
        return float(self._ds_currently.find("location/humidity").get("value"))

    @property
    def wind_speed(self):
        """Return the wind speed."""
        # Convert mps to kmh and round to .2 decimal.
        return round((float(self._ds_currently.find("location/windSpeed").get("mps"))*18)/5, 2)

    @property
    def wind_bearing(self):
        """Return the wind bearing."""
        return self._ds_currently.find("location/windDirection").get("name")

    @property
    def pressure(self):
        """Return the pressure."""
        return float(self._ds_currently.find("location/pressure").get("value"))

    @property
    def condition(self):
        """Return the weather condition."""
        return MAP_CONDITION.get(self._ds_root.find("./product/time/[@to='{}']/location/symbol".format(self._ds_currently.get("to"))).get("number"), "exceptional")

    @property
    def forecast(self):
        data = None

        data = [{
            ATTR_FORECAST_TIME:
                dt_util.parse_datetime(entry.get("to")),
            ATTR_FORECAST_TEMP:
                float(entry.find("location/temperature").get("value")),
            ATTR_FORECAST_PRECIPITATION:
                float(self._ds_root.find("./product/time/[@to='{}']/location/precipitation".format(entry.get("to"))).get("value")),
            ATTR_FORECAST_WIND_SPEED:
                round((float(entry.find("location/windSpeed").get("mps"))*18)/5, 2),
            ATTR_FORECAST_WIND_BEARING:
                entry.find("location/windDirection").get("name"),
            ATTR_FORECAST_CONDITION:
                MAP_CONDITION.get(self._ds_root.find("./product/time/[@to='{}']/location/symbol".format(entry.get("to"))).get("number"), "exceptional")
        } for entry in self._ds_data]

        return data

    def update(self):
        self._yr.update()
        self._ds_root = self._yr.root
        self._ds_data = self._yr.data
        self._ds_currently = self._yr.currently

class YrData:
    """Get the latest data from YR."""

    def __init__(self, latitude, longitude):
        self.latitude = latitude
        self.longitude = longitude

        self.root = None
        self.data = None
        self.currently = None

    @Throttle(MIN_TIME_BETWEEN_UPDATES)
    def update(self):
        """Get the latest data from YR."""

        try:
            url = 'https://api.met.no/weatherapi/locationforecastlts/1.3/?lat={}&lon={}'.format(self.latitude, self.longitude)
            resp = requests.get(url)
            self.root = ET.fromstring(resp.content)
            self.data = self.root.findall("./product/time[@datatype='forecast']/location/temperature/../..")
            self.currently = self.root.find("./product/time[@datatype='forecast']/location/temperature/../..")
        except (ConnectError, HTTPError, Timeout, ValueError) as error:
            _LOGGER.error("Unable to connect to Dark Sky. %s", error)
            self.data = None
