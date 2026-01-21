"""Configuration for Idealo Scraper."""
from dataclasses import dataclass
from typing import Dict

@dataclass
class CountryConfig:
    """Configuration for a specific Idealo country."""
    code: str
    domain: str
    site_id: int  # For GraphQL API (deprecated but kept for reference)
    currency: str
    language: str
    search_path: str  # Path for web search (e.g., /prechcat.html?q=)

# Country configurations
COUNTRIES: Dict[str, CountryConfig] = {
    "fr": CountryConfig(
        code="fr",
        domain="www.idealo.fr",
        site_id=4,
        currency="EUR",
        language="fr-FR",
        search_path="/prechcat.html?q=",
    ),
    "de": CountryConfig(
        code="de",
        domain="www.idealo.de",
        site_id=1,
        currency="EUR",
        language="de-DE",
        search_path="/preisvergleich/MainSearchProductCategory.html?q=",
    ),
    "uk": CountryConfig(
        code="uk",
        domain="www.idealo.co.uk",
        site_id=3,
        currency="GBP",
        language="en-GB",
        search_path="/mscat.html?q=",
    ),
    "es": CountryConfig(
        code="es",
        domain="www.idealo.es",
        site_id=11,
        currency="EUR",
        language="es-ES",
        search_path="/resultados.html?q=",
    ),
    "it": CountryConfig(
        code="it",
        domain="www.idealo.it",
        site_id=10,
        currency="EUR",
        language="it-IT",
        search_path="/risultati.html?q=",
    ),
    "at": CountryConfig(
        code="at",
        domain="www.idealo.at",
        site_id=2,
        currency="EUR",
        language="de-AT",
        search_path="/preisvergleich/MainSearchProductCategory.html?q=",  # Same as DE
    ),
}


# Default headers for requests
DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,fr;q=0.8,de;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
}

# User-Agent strings for rotation (Chrome-based to match curl_cffi impersonation)
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def get_random_user_agent() -> str:
    """Get a random User-Agent string from the rotation pool."""
    import random
    return random.choice(USER_AGENTS)


# Rate limiting defaults
DEFAULT_DELAY_SECONDS = 1.0
DEFAULT_MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

# GraphQL API endpoint (same for all countries)
GRAPHQL_ENDPOINT = "https://app.idealo.de/app-backend/api"

