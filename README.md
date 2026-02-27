<div align="center">

# 🗑️ Cornwall Waste Collection Calendar Generator

Automatically fetches upcoming Cornwall Council waste collection dates and generates an iCalendar (`.ics`) feed you can subscribe to in Apple Calendar, Google Calendar, Outlook, and other calendar apps.

</div>

---

## 📚 Table of Contents

- [⚡ Quick Start](#-quick-start)
- [✨ Features](#-features)
- [📦 Installation](#-installation)
- [🚀 Usage](#-usage)
- [⚙️ Configuration](#️-configuration)
- [🤖 GitHub Actions Automation](#-github-actions-automation)
- [📲 Subscribe in Calendar Apps](#-subscribe-in-calendar-apps)
- [🧩 Dependencies](#-dependencies)
- [🛠️ Troubleshooting](#️-troubleshooting)
- [⚠️ Known Limitations](#️-known-limitations)
- [📄 License](#-license)

---

## ⚡ Quick Start

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

✅ Output file: `cornwall_collection.ics`

---

## ✨ Features

| Feature | Description |
|---|---|
| `🗑️ Flexible Collection Support` | Scrapes Food, Recycling, Rubbish, and Garden dates from Cornwall Council services. |
| `🧭 Multiple Lookup Paths` | Supports `UPRN` lookup or `POSTCODE` + `HOUSE_NUMBER_OR_NAME`. |
| `🧹 Smart Filtering` | Includes `INCLUDE_*` toggles plus `ENABLE_COLLECTIONS`/`DISABLE_COLLECTIONS` precedence. |
| `📅 iCalendar Output` | Generates RFC 5545-compatible `.ics` events with stable deterministic UIDs. |
| `🌐 HTTP Reliability` | Configurable timeout, retries, and optional conditional HTTP cache (`ETag`/`Last-Modified`). |
| `🤖 GitHub Actions Ready` | Scheduled automation updates calendar output and can open failure issues automatically. |

---

## 📦 Installation

```bash
git clone https://github.com/evenwebb/cornwall-waste-collection-calendar-generator.git
cd cornwall-waste-collection-calendar-generator
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 🚀 Usage

### 🏠 UPRN lookup

```bash
export UPRN="100040118005"
python3 cornwall_collection.py
```

### 📮 Postcode + house lookup

```bash
export POSTCODE="TR1 1AA"
export HOUSE_NUMBER_OR_NAME="10"
python3 cornwall_collection.py
```

### 🎯 Only include selected collections

```bash
export ENABLE_COLLECTIONS="Food,Recycling"
python3 cornwall_collection.py
```

---

## ⚙️ Configuration

All settings are optional unless stated otherwise.

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
| `ENABLE_COLLECTIONS` | No | - | Comma-separated allow list (e.g. `Food,Recycling`). |
| `DISABLE_COLLECTIONS` | No | - | Comma-separated deny list (overrides allow list). |
| `FAIL_ON_EMPTY` | No | `false` | Exit with error if no events remain after filtering. |
| `OUTPUT_FILENAME` | No | `cornwall_collection.ics` | Output file path/name. |
| `TITLE` | No | `Cornwall Council` | Calendar title metadata. |
| `DESCRIPTION` | No | `Source for cornwall.gov.uk services for Cornwall Council` | Event description metadata. |
| `URL` | No | `https://cornwall.gov.uk` | Source URL metadata. |
| `USER_AGENT` | No | `Cornwall-Waste-Calendar-Generator/1.0` | HTTP User-Agent header. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`. |
| `REQUEST_TIMEOUT` | No | `10` | HTTP timeout in seconds. |
| `REQUEST_MAX_RETRIES` | No | `2` | Retry count for transient HTTP failures. |
| `REQUEST_RETRY_BACKOFF` | No | `1.0` | Retry backoff factor. |
| `ENABLE_HTTP_CACHE` | No | `true` | Enable conditional HTTP caching (`ETag` / `Last-Modified`). |
| `HTTP_CACHE_FILE` | No | `.http_cache.json` | Cache metadata file path. |

`*` Provide either `UPRN`, or `POSTCODE` (plus `HOUSE_NUMBER_OR_NAME` if strict matching is enabled).

### 🔢 Filter precedence

1. `INCLUDE_*` flags
2. `ENABLE_COLLECTIONS` allow list (if set)
3. `DISABLE_COLLECTIONS` deny list (always final)

---

## 🤖 GitHub Actions Automation

This repo includes `.github/workflows/scrape.yml`:

- `⏰` Runs daily at `06:00 UTC`
- `🖱️` Supports manual runs (`workflow_dispatch`)
- `🔁` Retries scraper runs before failing (`SCRAPER_RUN_ATTEMPTS`, default `2`)
- `📝` Commits updated output/cache files only when changed
- `🚨` Optionally opens or updates a GitHub issue on failure (`CREATE_FAILURE_ISSUE=true`)

Set repository secrets for runtime config (same variables as `.env.example`).

Recommended workflow-specific secrets:

- `SCRAPER_RUN_ATTEMPTS` (integer)
- `CREATE_FAILURE_ISSUE` (`true`/`false`)

---

## 📲 Subscribe in Calendar Apps

Use your raw GitHub `.ics` URL as a subscription URL:

`https://raw.githubusercontent.com/<github-user>/cornwall-waste-collection-calendar-generator/<branch>/<output-file>.ics`

Example:

`https://raw.githubusercontent.com/evenwebb/cornwall-waste-collection-calendar-generator/main/cornwall_collection.ics`

### 🗓️ Google Calendar

1. Open Google Calendar on web.
2. Click **+** next to **Other calendars**.
3. Select **From URL**.
4. Paste the raw `.ics` URL.

### 🍎 iPhone / iPad

1. Open **Settings**.
2. Go to **Calendar** -> **Accounts** -> **Add Account** -> **Other**.
3. Tap **Add Subscribed Calendar**.
4. Paste the raw `.ics` URL.

### 🤖 Android

1. Add the subscription in Google Calendar web using **From URL**.
2. Ensure that calendar is enabled in your Android calendar app sync settings.

---

## 🧩 Dependencies

| Package | Purpose |
|---|---|
| `requests` | HTTP requests to Cornwall Council endpoints |
| `beautifulsoup4` | HTML parsing for lookup and collection extraction |

---

## 🛠️ Troubleshooting

- `🔍` If no collections are found, verify `UPRN` or postcode/address values.
- `🏡` If using postcode mode, confirm `HOUSE_NUMBER_OR_NAME` matches council formatting.
- `📣` Set `LOG_LEVEL=DEBUG` for more verbose diagnostics.
- `🚫` Use `FAIL_ON_EMPTY=true` in CI to fail fast on empty calendars.

---

## ⚠️ Known Limitations

- `🧱` Parsing depends on Cornwall Council page/API response structure.
- `🕒` Calendar subscription refresh timing is controlled by each calendar provider/app.

---

## 📄 License

[GPL-3.0](LICENSE)
