<div align="center">

# Cornwall Waste Collection Calendar Generator

Automatically fetches upcoming Cornwall Council bin collection dates and publishes a continuously updated iCalendar (`.ics`) feed you can subscribe to from Apple Calendar, Google Calendar, Outlook, and other calendar apps.

[![License](https://img.shields.io/github/license/evenwebb/cornwall-waste-collection-calendar-generator)](https://github.com/evenwebb/cornwall-waste-collection-calendar-generator/blob/main/LICENSE)
[![Python](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org/)
[![Version](https://img.shields.io/badge/version-1.0.0-informational.svg)](https://github.com/evenwebb/cornwall-waste-collection-calendar-generator)
[![Scrape Workflow](https://github.com/evenwebb/cornwall-waste-collection-calendar-generator/actions/workflows/scrape.yml/badge.svg)](https://github.com/evenwebb/cornwall-waste-collection-calendar-generator/actions/workflows/scrape.yml)

</div>

---

## Table of Contents

- [Quick Start](#quick-start)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
- [Configuration](#configuration)
- [GitHub Actions Automation](#github-actions-automation)
- [Subscribe in Calendar Apps](#subscribe-in-calendar-apps)
- [Dependencies](#dependencies)
- [Troubleshooting](#troubleshooting)
- [Known Limitations](#known-limitations)
- [License](#license)
- [Support](#support)

---

## Quick Start

```bash
git clone https://github.com/evenwebb/cornwall-waste-collection-calendar-generator.git
cd cornwall-waste-collection-calendar-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your UPRN (or POSTCODE + HOUSE_NUMBER_OR_NAME)
python3 cornwall_collection.py
```

Output file: `cornwall_collection.ics`

---

## Features

- Scrapes latest collection dates from Cornwall Council.
- Generates RFC 5545-compatible `.ics` calendar events.
- Supports UPRN lookup or postcode + house matching.
- Per-collection filtering via `INCLUDE_*` flags.
- Advanced allow/deny filtering with `ENABLE_COLLECTIONS` and `DISABLE_COLLECTIONS`.
- Configurable network behavior (timeouts and retries).
- Optional daily GitHub Actions run that commits calendar updates.

---

## Installation

### Option 1: Run from source (recommended)

```bash
git clone https://github.com/evenwebb/cornwall-waste-collection-calendar-generator.git
cd cornwall-waste-collection-calendar-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Option 2: Install as a package

```bash
pip install .
```

Then run:

```bash
cornwall-collection
```

---

## Usage

### Example: UPRN lookup

```bash
export UPRN="100040118005"
python3 cornwall_collection.py
```

### Example: Postcode + house lookup

```bash
export POSTCODE="TR1 1AA"
export HOUSE_NUMBER_OR_NAME="10"
python3 cornwall_collection.py
```

### Example: Only generate Food + Recycling events

```bash
export ENABLE_COLLECTIONS="Food,Recycling"
python3 cornwall_collection.py
```

---

## Configuration

All settings are optional unless noted otherwise.

| Variable | Required | Default | Description |
|---|---|---|---|
| `UPRN` | Yes* | - | Unique Property Reference Number. |
| `POSTCODE` | Yes* | - | Alternative to `UPRN`. |
| `HOUSE_NUMBER_OR_NAME` | Depends | - | Required with `POSTCODE` when `STRICT_POSTCODE_MATCH=true`. |
| `STRICT_POSTCODE_MATCH` | No | `true` | Require house match for postcode lookups. |
| `INCLUDE_FOOD` | No | enabled | Set `false` to exclude food events. |
| `INCLUDE_RECYCLING` | No | enabled | Set `false` to exclude recycling events. |
| `INCLUDE_RUBBISH` | No | enabled | Set `false` to exclude rubbish events. |
| `INCLUDE_GARDEN` | No | enabled | Set `false` to exclude garden events. |
| `ENABLE_COLLECTIONS` | No | - | Comma-separated allow-list (e.g. `Food,Recycling`). |
| `DISABLE_COLLECTIONS` | No | - | Comma-separated deny-list (wins over allow-list). |
| `FAIL_ON_EMPTY` | No | `false` | Exit with error if no events remain after fetch/filtering. |
| `OUTPUT_FILENAME` | No | `cornwall_collection.ics` | Output file path/name. |
| `TITLE` | No | `Cornwall Council` | Calendar product title metadata. |
| `DESCRIPTION` | No | `Source for cornwall.gov.uk services for Cornwall Council` | Event description text. |
| `URL` | No | `https://cornwall.gov.uk` | Event source URL metadata. |
| `USER_AGENT` | No | `Cornwall-Waste-Calendar-Generator/1.0` | HTTP User-Agent header. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `REQUEST_TIMEOUT` | No | `10` | HTTP timeout seconds. |
| `REQUEST_MAX_RETRIES` | No | `2` | Retry count for transient HTTP failures. |
| `REQUEST_RETRY_BACKOFF` | No | `1.0` | Retry backoff factor. |

`*` You must provide either `UPRN`, or `POSTCODE` (plus `HOUSE_NUMBER_OR_NAME` if strict matching is enabled).

Filter precedence:

1. `INCLUDE_*` flags
2. `ENABLE_COLLECTIONS` allow-list (if set)
3. `DISABLE_COLLECTIONS` deny-list (always final)

---

## GitHub Actions Automation

This repo includes `.github/workflows/scrape.yml`:

- Runs daily at `06:00 UTC`
- Can be triggered manually (`workflow_dispatch`)
- Regenerates the `.ics` file
- Commits and pushes changes when output differs

Set the same variables from `.env.example` as GitHub repository secrets.

How it works for calendar subscriptions:

1. GitHub Action updates `cornwall_collection.ics` (or your `OUTPUT_FILENAME`).
2. The file is committed to your repository.
3. Your calendar app fetches that same URL on its own refresh schedule.
4. New collection dates appear automatically without manual re-import.

If your output file is public in the repo, use the raw GitHub URL pattern:

`https://raw.githubusercontent.com/<github-user>/<repo>/<branch>/<output-file>.ics`

Example:

`https://raw.githubusercontent.com/evenwebb/cornwall-waste-collection-calendar-generator/main/cornwall_collection.ics`

---

## Subscribe in Calendar Apps

Use your raw GitHub `.ics` URL as a **calendar subscription URL** (not a one-time file import).

> Note: For most apps, private GitHub repos will not work as a subscription feed without extra auth setup. Public repo is simplest.

### Google Calendar (Web)

1. Open Google Calendar in a browser.
2. In the left panel, next to **Other calendars**, click **+**.
3. Choose **From URL**.
4. Paste your raw GitHub `.ics` URL.
5. Click **Add calendar**.

### iPhone / iPad (Apple Calendar)

1. Open **Settings**.
2. Go to **Calendar** -> **Accounts** -> **Add Account** -> **Other**.
3. Tap **Add Subscribed Calendar**.
4. Paste your raw GitHub `.ics` URL.
5. Save.

### Android

Most Android calendar apps sync subscribed calendars via your Google account.

1. Add the calendar in Google Calendar (web) using **From URL**.
2. On Android, open your calendar app and ensure that subscribed calendar is enabled in sync/display settings.

If your Android app supports direct ICS subscriptions, you can paste the same raw GitHub URL directly in that app.

### Other Calendar Apps (Outlook, desktop apps, etc.)

Look for options named:

- `Subscribe from web`
- `Add calendar by URL`
- `Internet calendar`

Then paste the same raw GitHub `.ics` URL.

### Refresh Expectations

- Subscription refresh timing is controlled by each calendar provider/app.
- Changes pushed by GitHub Actions are not always instant in client apps.
- If updates seem delayed, wait for the next provider refresh cycle or re-open/sync the calendar app.

---

## Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to Cornwall Council endpoints |
| `beautifulsoup4` | HTML parsing for lookup and collection extraction |

---

## Troubleshooting

<details>
<summary><strong>No collections found</strong></summary>

- Verify `UPRN` or `POSTCODE` values are correct.
- If using postcode mode, confirm `HOUSE_NUMBER_OR_NAME` matches council address formatting.
- Set `LOG_LEVEL=DEBUG` for more verbose output.
- Use `FAIL_ON_EMPTY=true` in CI to fail fast when results are empty.

</details>

<details>
<summary><strong>Postcode lookup fails with strict match enabled</strong></summary>

- Provide `HOUSE_NUMBER_OR_NAME`.
- Or set `STRICT_POSTCODE_MATCH=false` to allow fallback to first match (not recommended for shared postcodes).

</details>

<details>
<summary><strong>Network or transient request errors</strong></summary>

- Increase `REQUEST_TIMEOUT`.
- Increase `REQUEST_MAX_RETRIES` and/or `REQUEST_RETRY_BACKOFF`.

</details>

---

## Known Limitations

- Parsing depends on Cornwall Council page structure; upstream HTML changes may break scraping.
- There is currently no automated test suite in this repository.

---

## License

Licensed under GPL-3.0-or-later. See [LICENSE](LICENSE).

---

## Support

- Open an issue: <https://github.com/evenwebb/cornwall-waste-collection-calendar-generator/issues>
- Repository: <https://github.com/evenwebb/cornwall-waste-collection-calendar-generator>

Built and maintained by [evenwebb](https://github.com/evenwebb).

If this project helps you, consider starring the repository.
