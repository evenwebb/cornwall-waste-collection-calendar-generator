from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

TITLE = "Cornwall Council"
DESCRIPTION = "Source for cornwall.gov.uk services for Cornwall Council"
URL = "https://cornwall.gov.uk"

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


def _is_enabled(collection_name: str) -> bool:
    """Return ``True`` if the given collection should be included."""
    env_var = INCLUDE_VARS.get(collection_name)
    value = os.getenv(env_var) if env_var else None
    if value is None:
        return True
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Collection:
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
    def __init__(
        self,
        uprn: str | None = None,
        postcode: str | None = None,
        housenumberorname: str | None = None,
    ) -> None:
        self._uprn = uprn
        self._postcode = postcode
        self._housenumberorname = str(housenumberorname) if housenumberorname else None

    def fetch(self) -> list[Collection]:
        entries: list[Collection] = []
        session = requests.Session()

        # Find the UPRN based on the postcode and the property name/number
        if self._uprn is None:
            args = {"Postcode": self._postcode}
            r = session.get(SEARCH_URLS["uprn_search"], params=args, timeout=10)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, features="html.parser")
            property_uprns = soup.find(id="Uprn").find_all("option")
            if len(property_uprns) == 0:
                raise SourceArgumentNotFound("postcode", str(self._postcode))
            for match in property_uprns:
                if match.text.startswith(self._housenumberorname or ""):
                    self._uprn = match["value"]
            if self._uprn is None:
                raise SourceArgumentNotFoundWithSuggestions(
                    "housenumberorname",
                    self._housenumberorname or "",
                    [match.text for match in property_uprns],
                )

        # Get the collection days based on the UPRN (either supplied through arguments or searched for above)
        args = {"uprn": self._uprn}
        r = session.get(SEARCH_URLS["collection_search"], params=args, timeout=10)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, features="html.parser")
        for collection_div in soup.find_all("div", class_="collection"):
            spans = collection_div.find_all("span")
            if not spans:
                continue
            collection = spans[0].text
            d = spans[-1].text + " " + str(date.today().year)
            name = NAME_MAP.get(collection, collection)
            entries.append(
                Collection(
                    datetime.strptime(d, "%d %b %Y").date(),
                    name,
                    icon=ICON_MAP.get(collection),
                )
            )

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


def main() -> None:
    """Fetch and print waste collection dates."""
    uprn = os.getenv("UPRN")
    postcode = os.getenv("POSTCODE")
    house = os.getenv("HOUSE_NUMBER_OR_NAME")
    source = Source(uprn=uprn, postcode=postcode, housenumberorname=house)
    try:
        collections = source.fetch()
    except Exception as exc:  # noqa: BLE001 - simple CLI feedback
        print(f"Error fetching data: {exc}")
        return

    collections = [c for c in collections if _is_enabled(c.type)]
    for c in collections:
        print(f"{c.date:%Y-%m-%d} - {c.type}")

    ics = _build_ics(collections)
    with open("cornwall_collection.ics", "w", encoding="utf-8") as f:
        f.write(ics)
    print("iCalendar file written to cornwall_collection.ics")


if __name__ == "__main__":
    main()
