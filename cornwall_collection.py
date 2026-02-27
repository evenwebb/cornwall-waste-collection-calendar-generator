from __future__ import annotations

import hashlib
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Calendar metadata defaults
DEFAULT_TITLE = "Cornwall Council"
DEFAULT_DESCRIPTION = "Source for cornwall.gov.uk services for Cornwall Council"
DEFAULT_URL = "https://cornwall.gov.uk"
DEFAULT_USER_AGENT = "Cornwall-Waste-Calendar-Generator/1.0"
DEFAULT_LOG_LEVEL = "INFO"

# Runtime defaults
DEFAULT_REQUEST_TIMEOUT = 10.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_RETRY_BACKOFF = 1.0
OUTPUT_FILENAME = "cornwall_collection.ics"
DEFAULT_HTTP_CACHE_FILE = ".http_cache.json"

SEARCH_URLS = {
    "uprn_search": "https://www.cornwall.gov.uk/my-area/",
    "collection_search": "https://www.cornwall.gov.uk/umbraco/Surface/Waste/MyCollectionDays?subscribe=False",
}

# Collection configuration (single source of truth).
COLLECTION_CONFIG = {
    "Food": {
        "summary": "Food Waste Collection",
        "icon": "mdi:food-apple",
        "include_env": "INCLUDE_FOOD",
    },
    "Recycling": {
        "summary": "Recycling Collection",
        "icon": "mdi:recycle",
        "include_env": "INCLUDE_RECYCLING",
    },
    "Rubbish": {
        "summary": "Rubbish Collection",
        "icon": "mdi:delete",
        "include_env": "INCLUDE_RUBBISH",
    },
    "Garden": {
        "summary": "Garden Waste Collection",
        "icon": "mdi:flower",
        "include_env": "INCLUDE_GARDEN",
    },
}
NAME_MAP = {key: value["summary"] for key, value in COLLECTION_CONFIG.items()}
ICON_MAP = {key: value["icon"] for key, value in COLLECTION_CONFIG.items()}
INCLUDE_VARS = {
    value["summary"]: value["include_env"] for value in COLLECTION_CONFIG.values()
}
COLLECTION_ALIASES = {
    token.casefold(): value["summary"]
    for token, value in COLLECTION_CONFIG.items()
} | {
    value["summary"].casefold(): value["summary"]
    for value in COLLECTION_CONFIG.values()
}

logger = logging.getLogger(__name__)


def _env_true(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_false(value: str) -> bool:
    return value.strip().lower() in {"0", "false", "no", "off"}


def _get_env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    if _env_true(value):
        return True
    if _env_false(value):
        return False
    logger.warning("Invalid boolean for %s=%r, using default %s", name, value, default)
    return default


def _get_env_int(name: str, default: int, minimum: int = 0) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = int(value)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, using default %d", name, value, default)
        return default
    if parsed < minimum:
        logger.warning(
            "Value for %s=%d is below minimum %d, using %d",
            name,
            parsed,
            minimum,
            minimum,
        )
        return minimum
    return parsed


def _get_env_float(name: str, default: float, minimum: float = 0.0) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        parsed = float(value)
    except ValueError:
        logger.warning("Invalid number for %s=%r, using default %.1f", name, value, default)
        return default
    if parsed < minimum:
        logger.warning(
            "Value for %s=%.2f is below minimum %.2f, using %.2f",
            name,
            parsed,
            minimum,
            minimum,
        )
        return minimum
    return parsed


def _get_env_csv(name: str) -> list[str]:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def _normalize_collection_name(name: str) -> str | None:
    return COLLECTION_ALIASES.get(name.casefold().strip())


def _parse_collection_tokens(items: list[str], source_name: str) -> set[str]:
    selections: set[str] = set()
    for item in items:
        normalized = _normalize_collection_name(item)
        if normalized is None:
            logger.warning(
                "Unknown collection in %s=%r. Valid values: %s",
                source_name,
                item,
                ", ".join(sorted(COLLECTION_ALIASES.keys())),
            )
            continue
        selections.add(normalized)
    return selections


def _configure_logging(log_level: str) -> None:
    resolved_log_level = getattr(logging, log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=resolved_log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    if not isinstance(getattr(logging, log_level.upper(), None), int):
        logger.warning(
            "Invalid LOG_LEVEL=%r, defaulting to %s",
            log_level,
            logging.getLevelName(resolved_log_level),
        )


def _is_enabled(collection_name: str) -> bool:
    """Return ``True`` if the given collection should be included."""
    env_var = INCLUDE_VARS.get(collection_name)
    value = os.getenv(env_var) if env_var else None
    if not value:
        return True
    return _env_true(value)


def _is_selected_by_lists(
    collection_name: str,
    enabled_collections: set[str],
    disabled_collections: set[str],
) -> bool:
    if enabled_collections and collection_name not in enabled_collections:
        return False
    if collection_name in disabled_collections:
        return False
    return True


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


class HttpResponseCache:
    def __init__(self, enabled: bool, filename: str) -> None:
        self._enabled = enabled
        self._filename = Path(filename)
        self._cache: dict[str, dict[str, str]] = {}

    def load(self) -> None:
        if not self._enabled or not self._filename.exists():
            return
        try:
            self._cache = json.loads(self._filename.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load HTTP cache file %s: %s", self._filename, exc)
            self._cache = {}

    def save(self) -> None:
        if not self._enabled:
            return
        try:
            self._filename.write_text(
                json.dumps(self._cache, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            logger.warning("Failed to save HTTP cache file %s: %s", self._filename, exc)

    @staticmethod
    def _cache_key(url: str, params: dict[str, str] | None) -> str:
        query = urlencode(sorted((params or {}).items()))
        return f"{url}?{query}"

    def get(
        self,
        url: str,
        params: dict[str, str] | None = None,
    ) -> dict[str, str] | None:
        if not self._enabled:
            return None
        return self._cache.get(self._cache_key(url, params))

    def set(
        self,
        url: str,
        params: dict[str, str] | None,
        *,
        body: str,
        etag: str | None,
        last_modified: str | None,
    ) -> None:
        if not self._enabled:
            return
        self._cache[self._cache_key(url, params)] = {
            "body": body,
            "etag": etag or "",
            "last_modified": last_modified or "",
        }


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


class EmptyCollectionsError(Exception):
    """Raised when no collections are found and strict empty handling is enabled."""


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
        user_agent: str = DEFAULT_USER_AGENT,
        request_timeout: float = DEFAULT_REQUEST_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        retry_backoff: float = DEFAULT_RETRY_BACKOFF,
        strict_postcode_match: bool = True,
        http_cache: HttpResponseCache | None = None,
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
        self._user_agent = user_agent
        self._request_timeout = request_timeout
        self._max_retries = max_retries
        self._retry_backoff = retry_backoff
        self._strict_postcode_match = strict_postcode_match
        self._http_cache = http_cache or HttpResponseCache(False, DEFAULT_HTTP_CACHE_FILE)

    @property
    def resolved_uprn(self) -> str | None:
        return self._uprn

    def _session_get(
        self,
        session: requests.Session,
        url: str,
        params: dict[str, str] | None = None,
    ) -> requests.Response:
        cached = self._http_cache.get(url, params)
        headers: dict[str, str] = {}
        if cached:
            etag = cached.get("etag")
            last_modified = cached.get("last_modified")
            if etag:
                headers["If-None-Match"] = etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

        response = session.get(
            url,
            params=params,
            timeout=self._request_timeout,
            headers=headers or None,
        )

        if response.status_code == 304:
            if not cached or not cached.get("body"):
                raise requests.HTTPError("Received 304 but no cached body is available")
            cached_response = requests.Response()
            cached_response.status_code = 200
            cached_response._content = cached["body"].encode("utf-8")
            cached_response.encoding = "utf-8"
            cached_response.url = response.url
            logger.debug("Using cached response body for %s", url)
            return cached_response

        response.raise_for_status()
        self._http_cache.set(
            url,
            params,
            body=response.text,
            etag=response.headers.get("ETag"),
            last_modified=response.headers.get("Last-Modified"),
        )
        return response

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
        current_year = today.year

        # Parse with current year first
        parsed_date = datetime.strptime(f"{date_str} {current_year}", "%d %b %Y").date()

        # The service returns upcoming collections; if this year is already in the past,
        # roll forward to the same date in the next year.
        if parsed_date < today:
            parsed_date = datetime.strptime(
                f"{date_str} {current_year + 1}", "%d %b %Y"
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
        headers = {"User-Agent": self._user_agent}

        with requests.Session() as session:
            session.headers.update(headers)
            retries = Retry(
                total=self._max_retries,
                connect=self._max_retries,
                read=self._max_retries,
                status=self._max_retries,
                backoff_factor=self._retry_backoff,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET"}),
            )
            adapter = HTTPAdapter(max_retries=retries)
            session.mount("https://", adapter)
            session.mount("http://", adapter)

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
                r = self._session_get(session, SEARCH_URLS["uprn_search"], args)
                soup = BeautifulSoup(r.text, features="html.parser")
                uprn_element = soup.find(id="Uprn")
                if uprn_element is None:
                    raise SourceArgumentNotFound("postcode", str(self._postcode))

                property_uprns = uprn_element.find_all("option")
                valid_uprns = [match for match in property_uprns if match.get("value")]
                if len(valid_uprns) == 0:
                    raise SourceArgumentNotFound("postcode", str(self._postcode))

                if self._housenumberorname:
                    house_query = self._housenumberorname.casefold().strip()
                    for match in valid_uprns:
                        if match.text.casefold().strip().startswith(house_query):
                            self._uprn = match["value"]
                            break
                elif self._strict_postcode_match:
                    raise ValueError(
                        "POSTCODE lookup requires HOUSE_NUMBER_OR_NAME when "
                        "STRICT_POSTCODE_MATCH is enabled"
                    )
                else:
                    self._uprn = valid_uprns[0]["value"]
                    logger.warning(
                        "HOUSE_NUMBER_OR_NAME not provided; defaulting to first "
                        "postcode match. Set STRICT_POSTCODE_MATCH=true to require "
                        "an explicit property match."
                    )

                if self._uprn is None:
                    raise SourceArgumentNotFoundWithSuggestions(
                        "housenumberorname",
                        self._housenumberorname or "",
                        [match.text for match in valid_uprns],
                    )
                logger.info("Found UPRN: %s", self._uprn)

            # Get the collection days based on the UPRN
            logger.info("Fetching collection dates for UPRN: %s", self._uprn)
            args = {"uprn": self._uprn}
            r = self._session_get(session, SEARCH_URLS["collection_search"], args)
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


def _escape_ics_text(value: str) -> str:
    """Escape text for ICS properties."""
    return (
        value.replace("\\", "\\\\")
        .replace(";", r"\;")
        .replace(",", r"\,")
        .replace("\n", r"\n")
    )


def _build_uid(collection: Collection, source_id: str) -> str:
    raw = f"{source_id}|{collection.date.isoformat()}|{collection.type}"
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"{digest}@cornwall-waste.local"


def _build_ics(
    collections: list[Collection],
    *,
    title: str,
    description: str,
    source_url: str,
    source_id: str,
) -> str:
    """Create an iCalendar file for the provided collections."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:-//{title}//Waste Collection//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    dtstamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for c in collections:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{_build_uid(c, source_id)}",
                f"SUMMARY:{_escape_ics_text(c.type)}",
                f"DESCRIPTION:{_escape_ics_text(description)}",
                f"URL:{_escape_ics_text(source_url)}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART;VALUE=DATE:{c.date:%Y%m%d}",
                f"DTEND;VALUE=DATE:{(c.date + timedelta(days=1)):%Y%m%d}",
                "END:VEVENT",
            ]
        )
        if c.icon:
            lines.insert(-1, f"X-ICON:{_escape_ics_text(c.icon)}")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def write_ics_file(
    collections: list[Collection],
    *,
    filename: str = OUTPUT_FILENAME,
    title: str = DEFAULT_TITLE,
    description: str = DEFAULT_DESCRIPTION,
    source_url: str = DEFAULT_URL,
    source_id: str = "default",
) -> None:
    """Write collections to an iCalendar file.

    Args:
        collections: List of Collection objects to write.
        filename: Output filename (default: from OUTPUT_FILENAME constant).
    """
    ics = _build_ics(
        collections,
        title=title,
        description=description,
        source_url=source_url,
        source_id=source_id,
    )
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


def validate_environment(
    strict_postcode_match: bool,
) -> tuple[str | None, str | None, str | None]:
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

    if postcode and strict_postcode_match and not house:
        raise ValueError(
            "POSTCODE is set but HOUSE_NUMBER_OR_NAME is missing while "
            "STRICT_POSTCODE_MATCH is enabled."
        )
    if postcode and not house:
        logger.warning(
            "POSTCODE is set but HOUSE_NUMBER_OR_NAME is not. "
            "Using first postcode match because STRICT_POSTCODE_MATCH is disabled."
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
        strict_postcode_match = _get_env_bool("STRICT_POSTCODE_MATCH", True)
        fail_on_empty = _get_env_bool("FAIL_ON_EMPTY", False)
        output_filename = os.getenv("OUTPUT_FILENAME", OUTPUT_FILENAME)
        request_timeout = _get_env_float(
            "REQUEST_TIMEOUT",
            DEFAULT_REQUEST_TIMEOUT,
            minimum=0.1,
        )
        max_retries = _get_env_int("REQUEST_MAX_RETRIES", DEFAULT_MAX_RETRIES, minimum=0)
        retry_backoff = _get_env_float(
            "REQUEST_RETRY_BACKOFF",
            DEFAULT_RETRY_BACKOFF,
            minimum=0.0,
        )
        enable_http_cache = _get_env_bool("ENABLE_HTTP_CACHE", True)
        http_cache_file = os.getenv("HTTP_CACHE_FILE", DEFAULT_HTTP_CACHE_FILE)
        enabled_collections = _parse_collection_tokens(
            _get_env_csv("ENABLE_COLLECTIONS"),
            "ENABLE_COLLECTIONS",
        )
        disabled_collections = _parse_collection_tokens(
            _get_env_csv("DISABLE_COLLECTIONS"),
            "DISABLE_COLLECTIONS",
        )
        title = os.getenv("TITLE", DEFAULT_TITLE)
        description = os.getenv("DESCRIPTION", DEFAULT_DESCRIPTION)
        source_url = os.getenv("URL", DEFAULT_URL)
        user_agent = os.getenv("USER_AGENT", DEFAULT_USER_AGENT)
        log_level = os.getenv("LOG_LEVEL", DEFAULT_LOG_LEVEL).upper()
        _configure_logging(log_level)

        # Validate environment and get configuration
        uprn, postcode, house = validate_environment(strict_postcode_match)
        logger.info("Starting Cornwall waste collection calendar generator")
        http_cache = HttpResponseCache(enable_http_cache, http_cache_file)
        http_cache.load()

        # Fetch collection data
        source = Source(
            uprn=uprn,
            postcode=postcode,
            housenumberorname=house,
            user_agent=user_agent,
            request_timeout=request_timeout,
            max_retries=max_retries,
            retry_backoff=retry_backoff,
            strict_postcode_match=strict_postcode_match,
            http_cache=http_cache,
        )
        collections = source.fetch()
        http_cache.save()

        if not collections:
            message = "No collections found"
            if fail_on_empty:
                raise EmptyCollectionsError(message)
            logger.warning(message)
            return

        # Filter based on user preferences
        original_count = len(collections)
        collections = [
            c
            for c in collections
            if _is_enabled(c.type)
            and _is_selected_by_lists(
                c.type,
                enabled_collections,
                disabled_collections,
            )
        ]
        filtered_count = original_count - len(collections)
        if filtered_count > 0:
            logger.info(
                "Filtered out %d collection(s) based on collection filtering settings",
                filtered_count,
            )
        if not collections:
            message = "No collections remain after filtering"
            if fail_on_empty:
                raise EmptyCollectionsError(message)
            logger.warning(message)
            return

        # Display and save results
        print_collections(collections)
        source_id = source.resolved_uprn or postcode or uprn or "unknown-property"
        write_ics_file(
            collections,
            filename=output_filename,
            title=title,
            description=description,
            source_url=source_url,
            source_id=source_id,
        )

        logger.info("Processing complete")

    except (
        ValueError,
        SourceArgumentNotFound,
        SourceArgumentNotFoundWithSuggestions,
        EmptyCollectionsError,
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
