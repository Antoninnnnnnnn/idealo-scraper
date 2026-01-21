"""Async version of Idealo Scraper using AsyncHttpClient."""
import asyncio
import re
import logging
from typing import Optional, List, Tuple

from .http_client import AsyncHttpClient
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
    DEFAULT_TIMEOUT,
    DEFAULT_MAX_RETRIES,
)
from .models import Product, Offer, ScrapeResult, SearchResult
from .exceptions import (
    IdealoError,
    ProductNotFoundError,
    IdealoBlockedError,
    RateLimitError,
)

logger = logging.getLogger(__name__)


class AsyncIdealoScraper:
    """
    Native async Idealo scraper using AsyncHttpClient.
    
    This is a true async implementation that uses the shared AsyncHttpClient
    for all HTTP concerns (rate limiting, retries, proxy rotation, TLS bypass).
    
    Usage:
        async with AsyncIdealoScraper() as scraper:
            results = await scraper.get_products_by_urls([url1, url2, url3])
    """
    
    def __init__(
        self,
        default_country: str = "fr",
        max_concurrent: int = 5,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
        proxy_url: Optional[str] = None,
        http_client: Optional[AsyncHttpClient] = None,
    ):
        """
        Initialize async scraper.
        
        Args:
            default_country: Default country code
            max_concurrent: Maximum concurrent requests
            delay_seconds: Delay between requests
            max_retries: Maximum retry attempts
            timeout: Request timeout in seconds
            proxy_url: Optional proxy URL
            http_client: Optional pre-configured AsyncHttpClient (for dependency injection/testing)
        """
        if default_country not in COUNTRIES:
            raise ValueError(f"Unknown country: {default_country}. Valid: {list(COUNTRIES.keys())}")
        
        self.default_country = default_country
        self.max_concurrent = max_concurrent
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.proxy_url = proxy_url
        
        # Use injected client or create new one
        if http_client is not None:
            self._client = http_client
            self._owns_client = False  # Don't close injected client
        else:
            self._client = AsyncHttpClient(
                delay_seconds=delay_seconds,
                max_retries=max_retries,
                timeout=timeout,
                max_concurrent=max_concurrent,
                proxy_url=proxy_url,
            )
            self._owns_client = True
    
    def _get_config(self, country: Optional[str] = None) -> CountryConfig:
        """Get country configuration."""
        country = country or self.default_country
        if country not in COUNTRIES:
            raise ValueError(f"Unknown country: {country}")
        return COUNTRIES[country]
    
    async def __aenter__(self):
        if self._owns_client:
            await self._client.__aenter__()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._owns_client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)
    
    async def _request(self, url: str, allow_redirects: bool = True) -> 'curl_cffi.Response':
        """Make a request using the http client."""
        return await self._client.get(url, allow_redirects=allow_redirects)
    
    async def get_product_by_url(self, url: str) -> ScrapeResult:
        """Scrape product data from an Idealo product URL."""
        # Detect country from URL
        from urllib.parse import urlparse
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
        
        product_id = extract_product_id(url)
        response = await self._request(url)
        html = response.text
        
        return self._parse_product_page(html, product_id, url, country)
    
    def _parse_product_page(
        self, 
        html: str, 
        product_id: str, 
        url: str, 
        country: str
    ) -> ScrapeResult:
        """Parse product page HTML to extract all data."""
        config = self._get_config(country)
        json_ld = extract_json_ld(html)
        product = parse_product_info(html, json_ld, product_id, url)
        offers = parse_offers(html, config)
        
        return ScrapeResult(
            product=product,
            offers=offers,
            country=country,
            currency=config.currency,
            raw_json_ld=json_ld,
        )
    
    async def get_product_by_id(self, product_id: str, country: Optional[str] = None) -> ScrapeResult:
        """Scrape product data by Idealo product ID."""
        config = self._get_config(country)
        
        url_patterns = {
            "de": f"https://{config.domain}/preisvergleich/OffersOfProduct/{product_id}",
            "at": f"https://{config.domain}/preisvergleich/OffersOfProduct/{product_id}",
            "fr": f"https://{config.domain}/prix/{product_id}/.html",
            "es": f"https://{config.domain}/precios/{product_id}/.html",
            "it": f"https://{config.domain}/prezzi/{product_id}/.html",
            "uk": f"https://{config.domain}/compare/{product_id}/.html",
        }
        url = url_patterns.get(config.code, f"https://{config.domain}/prix/{product_id}/.html")
        
        response = await self._request(url, allow_redirects=True)
        final_url = str(response.url)
        html = response.text
        
        return self._parse_product_page(html, str(product_id), final_url, config.code)
    
    async def search(
        self,
        query: str,
        country: Optional[str] = None,
        limit: int = 20,
        raise_errors: bool = False,
    ) -> List[SearchResult]:
        """
        Search for products using Idealo web search.
        
        Args:
            query: Search query
            country: Country code
            limit: Maximum results to return
            raise_errors: If True, raise exceptions instead of returning empty list
        """
        from urllib.parse import quote
        config = self._get_config(country)
        search_url = f"https://{config.domain}{config.search_path}{quote(query)}"
        
        try:
            response = await self._request(search_url, allow_redirects=True)
            final_url = str(response.url)
            
            # Check if redirected to a product page (exact match like EAN)
            if self._is_product_url(final_url):
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
    
    async def get_product_by_ean(self, ean: str, country: Optional[str] = None) -> Optional[ScrapeResult]:
        """Get full product data by EAN code."""
        config = self._get_config(country)
        
        # Validate EAN format
        if not re.match(r'^\d{8,14}$', ean):
            raise ValueError(f"Invalid EAN format: {ean}. Must be 8-14 digits.")
        
        search_url = f"https://{config.domain}/prechcat.html?q={ean}"
        
        try:
            response = await self._request(search_url, allow_redirects=True)
            final_url = str(response.url)
            
            if '/prix/' in final_url or '/preisvergleich/' in final_url:
                product_id = extract_product_id(final_url)
                return await self.get_product_by_url(final_url)
            else:
                results = parse_search_results(response.text, config)
                if results:
                    return await self.get_product_by_url(results[0].url)
                return None
                
        except ProductNotFoundError:
            return None
        except Exception as e:
            logger.warning(f"EAN search failed: {e}")
            return None
    
    async def get_products_by_urls(
        self,
        urls: List[str],
        return_exceptions: bool = True
    ) -> List[Tuple[str, ScrapeResult | Exception]]:
        """
        Scrape multiple product URLs in parallel.
        
        Args:
            urls: List of product URLs to scrape
            return_exceptions: If True, exceptions are returned instead of raised
            
        Returns:
            List of (url, result_or_exception) tuples
        """
        tasks = [self.get_product_by_url(url) for url in urls]
        
        if return_exceptions:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = await asyncio.gather(*tasks)
        
        return list(zip(urls, results))
    
    async def get_products_by_eans(
        self,
        eans: List[str],
        country: Optional[str] = None,
        return_exceptions: bool = True
    ) -> List[Tuple[str, Optional[ScrapeResult] | Exception]]:
        """
        Scrape multiple products by EAN in parallel.
        
        Args:
            eans: List of EAN codes
            country: Country code
            return_exceptions: If True, exceptions are returned instead of raised
            
        Returns:
            List of (ean, result_or_exception) tuples
        """
        tasks = [self.get_product_by_ean(ean, country) for ean in eans]
        
        if return_exceptions:
            results = await asyncio.gather(*tasks, return_exceptions=True)
        else:
            results = await asyncio.gather(*tasks)
        
        return list(zip(eans, results))
