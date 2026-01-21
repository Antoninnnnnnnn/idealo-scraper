"""Main Idealo Scraper implementation - Facade pattern."""
import re
import logging
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse, quote

from .http_client import HttpClient
from .parsing import (
    extract_product_id,
    extract_json_ld,
    parse_product_info,
    parse_offers,
    parse_search_results,
    extract_product_name_from_html,
)
from .config import (
    COUNTRIES,
    CountryConfig,
    DEFAULT_DELAY_SECONDS,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
)
from .models import Product, Offer, ScrapeResult, SearchResult
from .exceptions import (
    IdealoError,
    ProductNotFoundError,
    ParseError,
)

logger = logging.getLogger(__name__)


class IdealoScraper:
    """
    Modern Idealo scraper using curl_cffi for TLS fingerprint bypass.
    
    This is a facade class that coordinates:
    - HttpClient for requests
    - Parsing module for HTML/JSON processing
    
    Usage:
        with IdealoScraper() as scraper:
            result = scraper.get_product_by_url(url)
    """
    
    def __init__(
        self,
        default_country: str = "fr",
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
        proxy_url: Optional[str] = None,
        http_client: Optional[HttpClient] = None,
    ):
        """
        Initialize Idealo scraper.
        
        Args:
            default_country: Default country code (fr, de, uk, es, it, at)
            delay_seconds: Delay between requests
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
            proxy_url: Optional proxy URL (format: http://user:pass@host:port)
            http_client: Optional pre-configured HttpClient (for dependency injection/testing)
        """
        if default_country not in COUNTRIES:
            raise ValueError(f"Unknown country: {default_country}. Valid: {list(COUNTRIES.keys())}")
        
        self.default_country = default_country
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.proxy_url = proxy_url
        
        # For backwards compatibility
        self.proxies = None
        if proxy_url:
            self.proxies = {"http": proxy_url, "https": proxy_url}
        
        # Use injected client or create new one
        if http_client is not None:
            self._client = http_client
            self._owns_client = False  # Don't close injected client
        else:
            self._client = HttpClient(
                delay_seconds=delay_seconds,
                max_retries=max_retries,
                timeout=timeout,
                proxy_url=proxy_url,
            )
            self._owns_client = True
    
    def _get_config(self, country: Optional[str] = None) -> CountryConfig:
        """Get country configuration."""
        country = country or self.default_country
        if country not in COUNTRIES:
            raise ValueError(f"Unknown country: {country}")
        return COUNTRIES[country]
    
    def get_product_by_url(self, url: str) -> ScrapeResult:
        """
        Scrape product data from an Idealo product URL.
        
        Args:
            url: Full Idealo product URL
            
        Returns:
            ScrapeResult with product info and all offers
        """
        # Detect country from URL
        parsed = urlparse(url)
        domain = parsed.netloc
        country = None
        for code, config in COUNTRIES.items():
            if config.domain in domain:
                country = code
                break
        
        if not country:
            country = self.default_country
            logger.warning(f"Could not detect country from URL, using {country}")
        
        # Extract product ID from URL
        product_id = extract_product_id(url)
        
        # Fetch page
        response = self._client.get(url)
        html = response.text
        
        # Parse product data
        return self._parse_product_page(html, product_id, url, country)
    
    def get_product_by_id(self, product_id: str, country: Optional[str] = None) -> ScrapeResult:
        """
        Scrape product data by Idealo product ID.
        
        Args:
            product_id: Idealo product ID
            country: Country code (uses default if not specified)
            
        Returns:
            ScrapeResult with product info and all offers
        """
        config = self._get_config(country)
        
        # Construct URL based on country
        url_patterns = {
            "de": f"https://{config.domain}/preisvergleich/OffersOfProduct/{product_id}",
            "at": f"https://{config.domain}/preisvergleich/OffersOfProduct/{product_id}",
            "fr": f"https://{config.domain}/prix/{product_id}/.html",
            "es": f"https://{config.domain}/precios/{product_id}/.html",
            "it": f"https://{config.domain}/prezzi/{product_id}/.html",
            "uk": f"https://{config.domain}/compare/{product_id}/.html",
        }
        url = url_patterns.get(config.code, f"https://{config.domain}/prix/{product_id}/.html")
        
        response = self._client.get(url, allow_redirects=True)
        final_url = str(response.url)
        html = response.text
        
        return self._parse_product_page(html, str(product_id), final_url, config.code)
    
    def _parse_product_page(
        self, 
        html: str, 
        product_id: str, 
        url: str, 
        country: str
    ) -> ScrapeResult:
        """Parse product page HTML to extract all data."""
        config = self._get_config(country)
        
        # Extract JSON-LD data
        json_ld = extract_json_ld(html)
        
        # Parse product info
        product = parse_product_info(html, json_ld, product_id, url)
        
        # Parse all offers
        offers = parse_offers(html, config)
        
        return ScrapeResult(
            product=product,
            offers=offers,
            country=country,
            currency=config.currency,
            raw_json_ld=json_ld,
        )
    
    def search(
        self,
        query: str,
        country: Optional[str] = None,
        limit: int = 20,
        raise_errors: bool = False,
    ) -> List[SearchResult]:
        """
        Search for products using Idealo web search.
        
        Args:
            query: Search query (text or EAN code)
            country: Country code (fr, de, uk, es, it, at)
            limit: Maximum results to return
            raise_errors: If True, raise exceptions instead of returning empty list
            
        Returns:
            List of SearchResult objects
        """
        config = self._get_config(country)
        search_url = f"https://{config.domain}{config.search_path}{quote(query)}"
        
        try:
            response = self._client.get(search_url, allow_redirects=True)
            final_url = str(response.url)
            
            # Check if redirected to a product page (exact match like EAN)
            is_product_page = self._is_product_url(final_url)
            
            if is_product_page:
                product_id = extract_product_id(final_url)
                name = extract_product_name_from_html(response.text)
                
                return [SearchResult(
                    product_id=product_id,
                    name=name,
                    url=final_url,
                )]
            else:
                results = parse_search_results(response.text, config)
                return results[:limit]
                
        except ProductNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"Search failed: {e}")
            if raise_errors:
                raise
            return []
    
    def _is_product_url(self, url: str) -> bool:
        """Check if URL is a product page (not category)."""
        product_patterns = [
            re.compile(r'/prix/(\d+)/'),
            re.compile(r'/preisvergleich/OffersOfProduct/(\d+)'),
            re.compile(r'/preisvergleich/(\d+)/[^P]'),
            re.compile(r'/compare/(\d+)/'),
            re.compile(r'/confronta-prezzi/(\d+)/'),
            re.compile(r'/precios/(\d+)/'),
        ]
        
        for pattern in product_patterns:
            if pattern.search(url):
                return True
        return False
    
    def search_by_ean(
        self,
        ean: str,
        country: Optional[str] = None,
    ) -> List[SearchResult]:
        """
        Search for products by EAN/GTIN code.
        
        Args:
            ean: EAN/GTIN barcode (8-14 digits)
            country: Country code
            
        Returns:
            List of matching SearchResult objects
        """
        config = self._get_config(country)
        
        # Validate EAN format
        if not re.match(r'^\d{8,14}$', ean):
            raise ValueError(f"Invalid EAN format: {ean}. Must be 8-14 digits.")
        
        search_url = f"https://{config.domain}/prechcat.html?q={ean}"
        
        try:
            response = self._client.get(search_url, allow_redirects=True)
            final_url = str(response.url)
            
            if '/prix/' in final_url or '/preisvergleich/' in final_url:
                product_id = extract_product_id(final_url)
                name = extract_product_name_from_html(response.text)
                
                return [SearchResult(
                    product_id=product_id,
                    name=name,
                    url=final_url,
                    ean=ean,
                )]
            else:
                return parse_search_results(response.text, config)
                
        except ProductNotFoundError:
            return []
        except Exception as e:
            logger.warning(f"EAN search failed: {e}")
            return []
    
    def get_product_by_ean(
        self,
        ean: str,
        country: Optional[str] = None,
    ) -> Optional[ScrapeResult]:
        """
        Get full product data by EAN code.
        
        Args:
            ean: EAN/GTIN barcode
            country: Country code
            
        Returns:
            ScrapeResult if product found, None otherwise
        """
        results = self.search_by_ean(ean, country)
        
        if not results:
            logger.info(f"No products found for EAN: {ean}")
            return None
        
        first_result = results[0]
        return self.get_product_by_url(first_result.url)
    
    def close(self):
        """Close the HTTP client (only if we own it)."""
        if self._client and getattr(self, '_owns_client', True):
            self._client.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
