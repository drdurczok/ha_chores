# Home Chore Tracker for Home Assistant

This custom integration for Home Assistant helps you track chores around your home. It maintains a CSV database of your chore items and creates sensors that track how many days have passed since each item was last completed.

## Features

- Track chore status of various household items and areas
- CSV-based database for easy management of chore items
- Automatic sensors that show days since last chore completion
- Custom Lovelace cards to show chore status and instructions
- One-click "Mark as Done" functionality
- Visual indicators for items due for chores

## Installation

### Manual Installation

1. Copy the `home_chores_tracker` directory to your Home Assistant `custom_components` directory:
   ```
   /config/custom_components/home_chores_tracker/
   ```

2. Create a CSV file to store your chore data:
   ```
   /config/home_chores_tracker_data.csv
   ```

3. Add the following to your `configuration.yaml`:
   ```yaml
   home_chores_tracker:
     csv_path: "home_chores_tracker_data.csv"
   ```

4. Restart Home Assistant

### Using HACS (Home Assistant Community Store)

1. Add this repository to HACS as a custom repository
2. Install the "Home Chore Tracker" integration
3. Configure as described above

## CSV Data Format

The CSV file should have the following columns:

- `title`: Name of the item to be completed
- `date_last_chore`: Date when the item was last done (YYYY-MM-DD)
- `soft_deadline_days`: Number of days after which chore is recommended
- `hard_deadline_days`: Number of days after which chore is overdue
- `description`: Instructions or notes for chore the item

Example:

```csv
title,date_last_chore,soft_deadline_days,hard_deadline_days,description
AC Filters,2025-04-10,30,45,"Remove filters, wash with water, spray AC with fungal spray"
Bathroom,2025-05-05,5,10,"Clean toilet, sink, shower, and floor"
```

## Lovelace UI

### Example Cards

This integration provides sensors that you can use with conditional cards to display chore reminders. Here's an example card for tracking AC filter cleaning:

```yaml
type: conditional
conditions:
  - condition: numeric_state
    entity: sensor.days_since_ac_filters_cleaned
    above: 30
card:
  type: vertical-stack
  cards:
    - type: entity
      entity: sensor.days_since_ac_filters_cleaned
      icon: mdi:air-conditioner
      unit: days since clean
      name: AC Filter
    - type: markdown
      content: |-
        1. Remove filters from AC Unit.
        2. Wash with running water.
        3. Spray blue fins in AC with **AC Fungal Spray**
    - show_name: true
      show_icon: true
      type: button
      entity: script.mark_ac_filters_cleaned
      name: Mark Cleaned
      icon: mdi:check
      icon_height: 24px
      tap_action:
        action: call-service
        service: script.mark_ac_filters_cleaned
        data: {}
```

See the `example_lovelace_cards.yaml` file for more examples.

## Advanced Usage

### Services

The integration provides the following service:

- `home_chores_tracker.mark_done`: Mark an item as done
  - Parameters:
    - `item_id`: The ID of the item (lowercase title with spaces replaced by underscores)

Example service call:
```yaml
service: home_chores_tracker.mark_done
data:
  item_id: ac_filters
```

### Scripts

For each item in your CSV file, a script is automatically created with the name `script.mark_<item_id>_done`.

For example, for "AC Filters", a script called `script.mark_ac_filters_cleaned` will be created.

### Sensors

For each item in your CSV file, a sensor is created with the entity ID `sensor.days_since_<item_id>_done`.

Each sensor has the following attributes:
- `last_done`: Date when the item was last completed
- `soft_deadline`: Number of days after which chore is recommended
- `hard_deadline`: Number of days after which chore is overdue
- `description`: Instructions or notes for chore the item
- `status`: Current status (`ok`, `due_soon`, or `overdue`)

## Troubleshooting

- If your sensors are not updating, check the Home Assistant logs for any errors related to the `home_chores_tracker` component.
- Make sure your CSV file has the correct format and permissions.
- After making changes to the CSV file manually, you may need to restart Home Assistant or call the `homeassistant.reload_config_entry` service.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.