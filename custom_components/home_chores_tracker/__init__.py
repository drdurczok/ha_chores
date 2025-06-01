"""
Home Chores Tracker - Custom Home Assistant Integration

This integration tracks the chores status of various items in your home,
such as cleaning appliances, floors, etc. It maintains a CSV database of chores records
and provides sensors and scripts to manage chore tasks.
"""
import os
import csv
import logging
from datetime import datetime, timedelta
import voluptuous as vol

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers import discovery
from homeassistant.helpers.script import Script

_LOGGER = logging.getLogger(__name__)

DOMAIN = "home_chores_tracker"
DATA_CHORE_ITEMS = "chore_items"
DATA_CSV_PATH = "csv_path"

DEFAULT_SCAN_INTERVAL = timedelta(hours=1)
CSV_HEADER = [
    "title",
    "date_last_chore",
    "soft_deadline_days",
    "hard_deadline_days",
    "description",
]

PLATFORMS: list[str] = ["sensor"]


def _create_csv(path: str) -> None:
    """Create an empty CSV file with the default header."""
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(CSV_HEADER)


def _read_items(path: str):
    """Read all rows from the CSV file."""
    with open(path, "r", newline="") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]


def _write_items(path: str, items) -> None:
    """Write all items back to the CSV file."""
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADER)
        writer.writeheader()
        writer.writerows(items)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required("csv_path"): vol.All(str),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Home Chores Tracker component."""
    if DOMAIN not in config:
        return True

    csv_path = config[DOMAIN]["csv_path"]
    if not os.path.isabs(csv_path):
        csv_path = hass.config.path(csv_path)

    # Ensure the CSV file exists with proper headers
    if not os.path.isfile(csv_path):
        _LOGGER.warning(f"CSV file not found at {csv_path}")
        try:
            _LOGGER.info(f"Creating new chore tracker CSV at {csv_path}")
            await hass.async_add_executor_job(_create_csv, csv_path)
            _LOGGER.info(f"Successfully created new CSV file at {csv_path}")
        except Exception as e:
            _LOGGER.error(f"Failed to create CSV file at {csv_path}: {e}")
            return False

    hass.data[DOMAIN] = {
        DATA_CSV_PATH: csv_path,
        DATA_CHORE_ITEMS: {}
    }

    # Register services
    async def mark_done_service(call):
        """Mark an item as done."""
        item_id = call.data.get("item_id")
        if not item_id:
            _LOGGER.error("No item_id provided to mark_done service")
            return

        await mark_item_done(hass, item_id)

    hass.services.async_register(
        DOMAIN, 'mark_done', mark_done_service
    )

    await discovery.async_load_platform(
        hass,
        DOMAIN,
        "sensor",
        {},
        config,
    )

    # Load sensors from CSV
    await load_items_from_csv(hass)

    # Set up periodic refresh
    @callback
    def refresh_data(now=None):
        """Refresh data from CSV file."""
        hass.async_create_task(load_items_from_csv(hass))

    async_track_time_interval(hass, refresh_data, DEFAULT_SCAN_INTERVAL)

    # Set up scripts for each item
    setup_scripts(hass)

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Chores Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def mark_item_done(hass: HomeAssistant, item_id: str) -> None:
    """Mark a specific item as done today."""
    csv_path = hass.data[DOMAIN][DATA_CSV_PATH]
    items = []

    # Check if CSV file exists
    if not os.path.isfile(csv_path):
        _LOGGER.error(f"Cannot mark item as done: CSV file not found at {csv_path}")
        return

    # Read all items
    try:
        items = await hass.async_add_executor_job(_read_items, csv_path)
    except Exception as e:
        _LOGGER.error(f"Error reading CSV file at {csv_path}: {e}")
        return

    # Update the specified item
    found = False
    for item in items:
        if item["title"].lower().replace(" ", "_") == item_id:
            item["date_last_chore"] = datetime.now().strftime("%Y-%m-%d")
            found = True
            break

    if not found:
        _LOGGER.error(f"No item found with ID {item_id}")
        return

    # Write back to CSV
    try:
        await hass.async_add_executor_job(_write_items, csv_path, items)
        _LOGGER.info(f"Successfully marked {item_id} as done")
    except Exception as e:
        _LOGGER.error(f"Failed to write to CSV file at {csv_path}: {e}")
        return

    # Force refresh sensors
    await load_items_from_csv(hass)

async def load_items_from_csv(hass: HomeAssistant) -> None:
    """Load chore items from the CSV file."""
    csv_path = hass.data[DOMAIN][DATA_CSV_PATH]
    items = []

    # Check if CSV file exists
    if not os.path.isfile(csv_path):
        _LOGGER.error(f"Cannot load items: CSV file not found at {csv_path}")
        try:
            _LOGGER.info(f"Attempting to create a new CSV file at {csv_path}")
            await hass.async_add_executor_job(_create_csv, csv_path)
            _LOGGER.info(f"Successfully created new CSV file at {csv_path}")
        except Exception as e:
            _LOGGER.error(f"Failed to create CSV file at {csv_path}: {e}")
        return

    try:
        items = await hass.async_add_executor_job(_read_items, csv_path)

        hass.data[DOMAIN][DATA_CHORE_ITEMS] = items
        _LOGGER.debug(f"Loaded {len(items)} chore items from CSV")

        # Update sensor states
        for item in items:
            item_id = item["title"].lower().replace(" ", "_")
            sensor_entity_id = f"sensor.days_since_{item_id}_done"

            try:
                sensor = hass.states.get(sensor_entity_id)
                if sensor is not None:
                    # Calculate days since chore
                    try:
                        last_done = datetime.strptime(
                            item["date_last_chore"], "%Y-%m-%d"
                        )
                        days_since = (datetime.now() - last_done).days
                    except (ValueError, TypeError):
                        days_since = 999  # Default for items never done

                    hass.states.async_set(
                        sensor_entity_id,
                        days_since,
                        {
                            "friendly_name": f"{item['title']}",
                            "unit_of_measurement": "days",
                            "soft_deadline": item["soft_deadline_days"],
                            "hard_deadline": item["hard_deadline_days"],
                            "description": item["description"],
                            "last_done": item["date_last_chore"],
                        }
                    )
            except Exception as e:
                _LOGGER.error(f"Error updating sensor {sensor_entity_id}: {e}")

    except FileNotFoundError:
        _LOGGER.error(f"CSV file not found at {csv_path}")
    except PermissionError:
        _LOGGER.error(f"Permission denied when accessing CSV file at {csv_path}")
    except csv.Error as e:
        _LOGGER.error(f"CSV error when loading from {csv_path}: {e}")
    except Exception as e:
        _LOGGER.error(f"Error loading chore items from CSV: {e}")

def setup_scripts(hass: HomeAssistant) -> None:
    """Set up scripts for marking items as done."""
    items = hass.data[DOMAIN].get(DATA_CHORE_ITEMS, [])

    if not items:
        _LOGGER.warning("No chore items found for script setup - CSV may be missing or empty")
        return

    for item in items:
        item_id = item["title"].lower().replace(" ", "_")
        script_id = f"mark_{item_id}_done"

        # Create a script for each item
        sequence = [{
            "service": f"{DOMAIN}.mark_done",
            "data": {
                "item_id": item_id
            }
        }]

        script = Script(
            hass,
            sequence,
            f"Mark {item['title']} as Done",
            DOMAIN
        )

        # Register the script
        hass.services.async_register(
            "script", script_id, script.run
        )