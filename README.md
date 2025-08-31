# Cornwall Waste Collection Calendar Generator

This project fetches upcoming waste collection dates from the Cornwall Council website.
It uses a scraping mechanism adapted from the `waste_collection_schedule` project and builds an iCalendar (.ics) file. The generated calendar can be imported into any calendar application that supports the iCalendar format.

## Environment Variables

The script reads the following environment variables to determine the property for
which to fetch collection information:

- `UPRN` – Unique Property Reference Number. Set this to identify the property directly.
- `POSTCODE` – Postcode of the property (used when `UPRN` is not set).
- `HOUSE_NUMBER_OR_NAME` – House number or name (used with `POSTCODE`).

Optional variables allow disabling generation of specific collection types. If
unset, all events are created.

- `INCLUDE_FOOD` – set to `false` to skip Food Waste Collection events.
- `INCLUDE_RECYCLING` – set to `false` to skip Recycling Collection events.
- `INCLUDE_RUBBISH` – set to `false` to skip Rubbish Recycling events.
- `INCLUDE_GARDEN` – set to `false` to skip Garden Waste Collection events.

A sample environment file is provided as `.env.example`. When using the
included GitHub Actions workflow, add these variables (including any optional
`INCLUDE_*` values) as repository secrets.

## Usage

1. Configure the required environment variables. For example:

   ```bash
   export UPRN="100040118005"
   ```

   Alternatively, set `POSTCODE` and `HOUSE_NUMBER_OR_NAME` if the UPRN is not known.

2. Run the scraper:

   ```bash
   python cornwall_collection.py
   ```

The script will print upcoming collection dates and their types and also
generate an `cornwall_collection.ics` file that can be imported into any
calendar application supporting the iCalendar format.
