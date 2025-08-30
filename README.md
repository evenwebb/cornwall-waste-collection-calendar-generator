# Cornwall Waste Collection Calendar Generator

This project fetches upcoming waste collection dates from the Cornwall Council website.
It uses a scraping mechanism adapted from the `waste_collection_schedule` project.

## Environment Variables

The script reads the following environment variables to determine the property for
which to fetch collection information:

- `UPRN` – Unique Property Reference Number. Set this to identify the property directly.
- `POSTCODE` – Postcode of the property (used when `UPRN` is not set).
- `HOUSE_NUMBER_OR_NAME` – House number or name (used with `POSTCODE`).

A sample environment file is provided as `.env.example`.

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

The script will print upcoming collection dates and their types.
