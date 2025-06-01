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
from homeassistant.components.script import DOMAIN as SCRIPT_DOMAIN

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
    if not os.path.isfile(path):
        return []

    try:
        with open(path, "r", newline="") as f:
            reader = csv.DictReader(f)
            return [row for row in reader]
    except Exception as e:
        _LOGGER.error(f"Error reading CSV file {path}: {e}")
        return []


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

    # Initialize hass.data for this domain
    hass.data[DOMAIN] = {
        DATA_CSV_PATH: csv_path,
        DATA_CHORE_ITEMS: []
    }

    # Load items from CSV first
    await load_items_from_csv(hass)

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

    # Load sensor platform after data is loaded
    hass.async_create_task(
        discovery.async_load_platform(
            hass,
            "sensor",
            DOMAIN,
            {},
            config,
        )
    )

    # Set up periodic refresh
    @callback
    def refresh_data(now=None):
        """Refresh data from CSV file."""
        hass.async_create_task(load_items_from_csv(hass))

    async_track_time_interval(hass, refresh_data, DEFAULT_SCAN_INTERVAL)

    # Set up scripts for each item - delay this to ensure script platform is ready
    def setup_scripts_delayed():
        hass.async_create_task(setup_scripts(hass))

    # Schedule script setup after a short delay
    hass.loop.call_later(2, setup_scripts_delayed)

    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Home Chores Tracker from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def mark_item_done(hass: HomeAssistant, item_id: str) -> None:
    """Mark a specific item as done today."""
    csv_path = hass.data[DOMAIN][DATA_CSV_PATH]

    # Read all items
    items = await hass.async_add_executor_job(_read_items, csv_path)
    if not items:
        _LOGGER.error(f"No items found in CSV file at {csv_path}")
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

        if not items:
            _LOGGER.warning(f"No chores found in CSV at {csv_path}")
        else:
            _LOGGER.info(f"Loaded {len(items)} chore items from CSV")

    except Exception as e:
        _LOGGER.error(f"Error loading chore items from CSV: {e}")
        hass.data[DOMAIN][DATA_CHORE_ITEMS] = []

async def setup_scripts(hass: HomeAssistant) -> None:
    """Set up scripts for marking items as done."""
    items = hass.data[DOMAIN].get(DATA_CHORE_ITEMS, [])
    csv_path = hass.data[DOMAIN].get(DATA_CSV_PATH, "unknown")

    if not items:
        _LOGGER.warning(
            f"No chore items found for script setup - CSV may be missing or empty at {csv_path}"
        )
        return

    # Ensure script domain is initialized
    if SCRIPT_DOMAIN not in hass.data:
        hass.data[SCRIPT_DOMAIN] = {}

    for item in items:
        item_id = item["title"].lower().replace(" ", "_")
        script_id = f"mark_{item_id}_done"

        # Create script configuration
        script_config = {
            "alias": f"Mark {item['title']} as Done",
            "sequence": [{
                "service": f"{DOMAIN}.mark_done",
                "data": {
                    "item_id": item_id
                }
            }]
        }

        # Create the script entity directly
        try:
            from homeassistant.components.script import ScriptEntity

            script_entity = ScriptEntity(hass, script_id, script_config, True)

            # Register the script entity
            hass.data[SCRIPT_DOMAIN][script_id] = script_entity

            # Add to entity registry
            entity_id = f"script.{script_id}"
            hass.states.async_set(entity_id, "off", {
                "friendly_name": f"Mark {item['title']} as Done",
                "icon": "mdi:check-circle"
            })

            _LOGGER.info(f"Created script: {entity_id}")

        except Exception as e:
            _LOGGER.error(f"Failed to create script {script_id}: {e}")

            # Fallback: create a simple script using the Script helper
            try:
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

                # Store the script in a way that makes it accessible
                if "scripts" not in hass.data:
                    hass.data["scripts"] = {}
                hass.data["scripts"][script_id] = script

                _LOGGER.info(f"Created fallback script: {script_id}")

            except Exception as fallback_error:
                _LOGGER.error(f"Failed to create fallback script {script_id}: {fallback_error}")