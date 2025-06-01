"""
Sensor platform for Home Chore Tracker integration.
"""
import logging
from datetime import datetime, timedelta

from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.entity import Entity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import DOMAIN, DATA_CHORE_ITEMS

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(
        hass: HomeAssistant,
        config: ConfigType,
        async_add_entities: callable,
        discovery_info: DiscoveryInfoType = None,
):
    """Set up the chore tracker sensor platform."""
    if discovery_info is None:
        return

    items = hass.data[DOMAIN][DATA_CHORE_ITEMS]
    entities = []

    for item in items:
        entities.append(ChoreTrackerSensor(hass, item))

    async_add_entities(entities, True)


class ChoreTrackerSensor(SensorEntity):
    """Representation of a chore tracker sensor."""

    def __init__(self, hass, item):
        """Initialize the sensor."""
        self.hass = hass
        self._item = item
        self._name = item["title"]
        self._item_id = item["title"].lower().replace(" ", "_")
        self._days_since = None
        self._last_done = None
        self._soft_deadline = int(item["soft_deadline_days"])
        self._hard_deadline = int(item["hard_deadline_days"])
        self._description = item["description"]
        self._attr_unique_id = f"chore_tracker_{self._item_id}"
        self.entity_id = f"sensor.days_since_{self._item_id}_done"

    @property
    def name(self):
        """Return the name of the sensor."""
        return f"{self._name}"

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._days_since

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return "days"


    @property
    def icon(self):
        """Return the icon to use based on chore status."""
        if self._days_since is None:
            return "mdi:help-circle"

        if self._days_since > self._hard_deadline:
            return "mdi:alert-circle"
        elif self._days_since > self._soft_deadline:
            return "mdi:alert"
        else:
            return "mdi:check-circle"

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        return {
            "last_done": self._last_done,
            "soft_deadline": self._soft_deadline,
            "hard_deadline": self._hard_deadline,
            "description": self._description,
            "status": self._get_status(),
        }

    def _get_status(self):
        """Get the status of the chore item."""
        if self._days_since is None:
            return "unknown"

        if self._days_since > self._hard_deadline:
            return "overdue"
        elif self._days_since > self._soft_deadline:
            return "due_soon"
        else:
            return "ok"

    async def async_update(self):
        """Update the sensor."""
        # Find the current item data
        items = self.hass.data[DOMAIN][DATA_CHORE_ITEMS]

        for item in items:
            if item["title"] == self._name:
                self._item = item
                self._description = item["description"]
                self._soft_deadline = int(item["soft_deadline_days"])
                self._hard_deadline = int(item["hard_deadline_days"])

                try:
                    # Calculate days since chore
                    self._last_done = item["date_last_chore"]
                    if self._last_done:
                        last_done_date = datetime.strptime(
                            self._last_done, "%Y-%m-%d"
                        )
                        self._days_since = (datetime.now() - last_done_date).days
                    else:
                        self._days_since = 999  # Default for items never done
                except (ValueError, TypeError) as e:
                    _LOGGER.warning(f"Error calculating dates for {self._name}: {e}")
                    self._days_since = None

                break