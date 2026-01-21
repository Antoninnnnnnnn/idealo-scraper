"""Idealo Scraper - Modern multi-country price scraper for Idealo."""

from .scraper import IdealoScraper
from .async_scraper import AsyncIdealoScraper
from .models import Product, Offer, ScrapeResult, SearchResult
from .exceptions import (
    IdealoError,
    IdealoBlockedError,
    ProductNotFoundError,
    RateLimitError,
    ParseError,
)
from .config import COUNTRIES
from .http_client import HttpClient, AsyncHttpClient

__version__ = "2.1.0"
__all__ = [
    "IdealoScraper",
    "AsyncIdealoScraper",
    "HttpClient",
    "AsyncHttpClient",
    "Product",
    "Offer", 
    "ScrapeResult",
    "SearchResult",
    "IdealoError",
    "IdealoBlockedError",
    "ProductNotFoundError",
    "RateLimitError",
    "ParseError",
    "COUNTRIES",
]

