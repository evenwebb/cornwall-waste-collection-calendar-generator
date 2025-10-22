from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

# Configuration constants
TITLE = "Cornwall Council"
DESCRIPTION = "Source for cornwall.gov.uk services for Cornwall Council"
URL = "https://cornwall.gov.uk"
USER_AGENT = "Cornwall-Waste-Calendar-Generator/1.0"
REQUEST_TIMEOUT = 10
OUTPUT_FILENAME = "cornwall_collection.ics"

SEARCH_URLS = {
    "uprn_search": "https://www.cornwall.gov.uk/my-area/",
    "collection_search": "https://www.cornwall.gov.uk/umbraco/Surface/Waste/MyCollectionDays?subscribe=False",
}
ICON_MAP = {
    "Rubbish": "mdi:delete",
    "Recycling": "mdi:recycle",
    "Garden": "mdi:flower",
}

# Map the council's shorthand names to user-friendly summaries
NAME_MAP = {
    "Food": "Food Waste Collection",
    "Recycling": "Recycling Collection",
    "Rubbish": "Rubbish Recycling",
    "Garden": "Garden Waste Collection",
}

# Environment variable names to toggle individual collections. By default all
# events are created unless a value evaluates to ``false``.
INCLUDE_VARS = {
    "Food Waste Collection": "INCLUDE_FOOD",
    "Recycling Collection": "INCLUDE_RECYCLING",
    "Rubbish Recycling": "INCLUDE_RUBBISH",
    "Garden Waste Collection": "INCLUDE_GARDEN",
}

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def _is_enabled(collection_name: str) -> bool:
    """Return ``True`` if the given collection should be included."""
    env_var = INCLUDE_VARS.get(collection_name)
    value = os.getenv(env_var) if env_var else None
    if not value:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Collection:
    """Represents a single waste collection event.

    Attributes:
        date: The date of the collection.
        type: The type of collection (e.g., "Food Waste Collection").
        icon: Optional Material Design icon identifier for the collection type.
    """

    date: date
    type: str
    icon: str | None = None


class SourceArgumentNotFound(Exception):
    """Raised when a provided argument does not match any results."""

    def __init__(self, argument: str, value: str) -> None:
        message = f"Unable to find {argument}: {value}"
        super().__init__(message)


class SourceArgumentNotFoundWithSuggestions(Exception):
    """Raised when no exact match is found but suggestions exist."""

    def __init__(self, argument: str, value: str, suggestions: list[str]) -> None:
        suggestion_text = ", ".join(suggestions)
        message = (
            f"Unable to find {argument}: {value}. Did you mean one of: {suggestion_text}"
        )
        super().__init__(message)


class Source:
    """Fetches waste collection data from Cornwall Council website.

    This class handles both UPRN-based direct lookup and postcode/address-based
    searches to retrieve waste collection schedules.

    Attributes:
        _uprn: Unique Property Reference Number for direct lookup.
        _postcode: Postcode for address-based search.
        _housenumberorname: House number or name for address-based search.
    """

    def __init__(
        self,
        uprn: str | None = None,
        postcode: str | None = None,
        housenumberorname: str | None = None,
    ) -> None:
        """Initialize the Source with property identification parameters.

        Args:
            uprn: Unique Property Reference Number (optional).
            postcode: Postcode for property search (optional).
            housenumberorname: House number or name (optional).
        """
        self._uprn = uprn
        self._postcode = postcode
        self._housenumberorname = str(housenumberorname) if housenumberorname else None

    def _parse_collection_date(self, date_str: str) -> date:
        """Parse a collection date string, handling year boundaries correctly.

        The website returns dates in format "DD Mon" without year. We need to infer
        the year, accounting for the case where we're in December and the date shown
        is in January (next year) or vice versa.

        Args:
            date_str: Date string in format "DD Mon" (e.g., "15 Jan").

        Returns:
            A date object representing the collection date.
        """
        today = date.today()
        current_month = today.month
        current_year = today.year

        # Parse with current year first
        parsed_date = datetime.strptime(f"{date_str} {current_year}", "%d %b %Y").date()

        # If we're in December (month 12) and the parsed date is in January/February (months 1-2),
        # the date is likely in the next year
        if current_month == 12 and parsed_date.month <= 2:
            parsed_date = datetime.strptime(
                f"{date_str} {current_year + 1}", "%d %b %Y"
            ).date()
        # If we're in January (month 1) and the parsed date is in December (month 12),
        # the date might be from last year (though this is less common for future collections)
        elif current_month == 1 and parsed_date.month == 12:
            if parsed_date < today:
                parsed_date = datetime.strptime(
                    f"{date_str} {current_year - 1}", "%d %b %Y"
                ).date()

        return parsed_date

    def fetch(self) -> list[Collection]:
        """Fetch waste collection dates from Cornwall Council website.

        Returns:
            A list of Collection objects representing upcoming waste collections.

        Raises:
            SourceArgumentNotFound: If the postcode or UPRN cannot be found.
            SourceArgumentNotFoundWithSuggestions: If the house number/name doesn't
                match but similar addresses exist.
            requests.HTTPError: If the HTTP request fails.
        """
        entries: list[Collection] = []
        headers = {"User-Agent": USER_AGENT}

        with requests.Session() as session:
            session.headers.update(headers)

            # Find the UPRN based on the postcode and the property name/number
            if self._uprn is None:
                if not self._postcode:
                    raise ValueError(
                        "Either UPRN or POSTCODE must be provided"
                    )

                logger.info(
                    "Looking up UPRN for postcode: %s, house: %s",
                    self._postcode,
                    self._housenumberorname,
                )
                args = {"Postcode": self._postcode}
                r = session.get(
                    SEARCH_URLS["uprn_search"], params=args, timeout=REQUEST_TIMEOUT
                )
                r.raise_for_status()
                soup = BeautifulSoup(r.text, features="html.parser")
                uprn_element = soup.find(id="Uprn")
                if uprn_element is None:
                    raise SourceArgumentNotFound("postcode", str(self._postcode))

                property_uprns = uprn_element.find_all("option")
                if len(property_uprns) == 0:
                    raise SourceArgumentNotFound("postcode", str(self._postcode))

                for match in property_uprns:
                    if match.text.startswith(self._housenumberorname or ""):
                        self._uprn = match["value"]
                        break

                if self._uprn is None:
                    raise SourceArgumentNotFoundWithSuggestions(
                        "housenumberorname",
                        self._housenumberorname or "",
                        [match.text for match in property_uprns],
                    )
                logger.info("Found UPRN: %s", self._uprn)

            # Get the collection days based on the UPRN
            logger.info("Fetching collection dates for UPRN: %s", self._uprn)
            args = {"uprn": self._uprn}
            r = session.get(
                SEARCH_URLS["collection_search"], params=args, timeout=REQUEST_TIMEOUT
            )
            r.raise_for_status()
            soup = BeautifulSoup(r.text, features="html.parser")

            for collection_div in soup.find_all("div", class_="collection"):
                spans = collection_div.find_all("span")
                if not spans:
                    continue
                collection = spans[0].text.strip()
                date_str = spans[-1].text.strip()
                name = NAME_MAP.get(collection, collection)

                try:
                    collection_date = self._parse_collection_date(date_str)
                    entries.append(
                        Collection(
                            collection_date,
                            name,
                            icon=ICON_MAP.get(collection),
                        )
                    )
                except ValueError as e:
                    logger.warning(
                        "Failed to parse date '%s' for collection '%s': %s",
                        date_str,
                        collection,
                        e,
                    )
                    continue

            logger.info("Found %d collection entries", len(entries))

        return entries


def _build_ics(collections: list[Collection]) -> str:
    """Create an iCalendar file for the provided collections."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{TITLE}//Waste Collection//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for c in collections:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{c.date:%Y%m%d}-{c.type.replace(' ', '')}@{URL}",
                f"SUMMARY:{c.type}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{c.date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{(c.date + timedelta(days=1)):%Y%m%d}",
                "END:VEVENT",
            ]
        )
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_ics_file(collections: list[Collection], filename: str = OUTPUT_FILENAME) -> None:
    """Write collections to an iCalendar file.

    Args:
        collections: List of Collection objects to write.
        filename: Output filename (default: from OUTPUT_FILENAME constant).
    """
    ics = _build_ics(collections)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(ics)
    logger.info("iCalendar file written to %s", filename)


def print_collections(collections: list[Collection]) -> None:
    """Print collection dates to stdout in a formatted manner.

    Args:
        collections: List of Collection objects to print.
    """
    if not collections:
        logger.warning("No collections to display")
        return

    logger.info("Upcoming waste collections:")
    for c in collections:
        print(f"{c.date:%Y-%m-%d} - {c.type}")


def validate_environment() -> tuple[str | None, str | None, str | None]:
    """Validate and retrieve environment variables.

    Returns:
        Tuple of (uprn, postcode, house_number_or_name).

    Raises:
        ValueError: If required environment variables are missing.
    """
    uprn = os.getenv("UPRN")
    postcode = os.getenv("POSTCODE")
    house = os.getenv("HOUSE_NUMBER_OR_NAME")

    if not uprn and not postcode:
        raise ValueError(
            "Either UPRN or POSTCODE environment variable must be set. "
            "See README.md for configuration details."
        )

    if postcode and not house:
        logger.warning(
            "POSTCODE is set but HOUSE_NUMBER_OR_NAME is not. "
            "This may result in matching the first property at the postcode."
        )

    return uprn, postcode, house


def main() -> None:
    """Fetch and print waste collection dates, then generate an iCalendar file.

    This is the main entry point for the application. It:
    1. Validates environment variables
    2. Fetches collection data from Cornwall Council
    3. Filters collections based on user preferences
    4. Prints collection dates to stdout
    5. Generates an iCalendar (.ics) file

    Exits with status code 1 on error.
    """
    try:
        # Validate environment and get configuration
        uprn, postcode, house = validate_environment()
        logger.info("Starting Cornwall waste collection calendar generator")

        # Fetch collection data
        source = Source(uprn=uprn, postcode=postcode, housenumberorname=house)
        collections = source.fetch()

        if not collections:
            logger.warning("No collections found")
            return

        # Filter based on user preferences
        original_count = len(collections)
        collections = [c for c in collections if _is_enabled(c.type)]
        filtered_count = original_count - len(collections)
        if filtered_count > 0:
            logger.info(
                "Filtered out %d collection(s) based on INCLUDE_* settings",
                filtered_count,
            )

        # Display and save results
        print_collections(collections)
        write_ics_file(collections)

        logger.info("Processing complete")

    except (
        ValueError,
        SourceArgumentNotFound,
        SourceArgumentNotFoundWithSuggestions,
    ) as exc:
        logger.error("Configuration or lookup error: %s", exc)
        sys.exit(1)
    except requests.RequestException as exc:
        logger.error("Network error while fetching data: %s", exc)
        sys.exit(1)
    except Exception as exc:
        logger.exception("Unexpected error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
