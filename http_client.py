"""HTTP client with rate limiting, retries, and TLS fingerprint bypass."""
import time
import logging
import threading
import uuid
from typing import Optional, Dict, Any, List, Union

from curl_cffi import requests as curl_requests

from .config import DEFAULT_HEADERS, DEFAULT_DELAY_SECONDS, DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT, get_random_user_agent
from .exceptions import IdealoError, IdealoBlockedError, ProductNotFoundError, RateLimitError
from .logging_utils import get_logger, set_request_context

logger = get_logger(__name__)

class HttpClient:
    """
    HTTP client for Idealo with:
    - TLS fingerprint bypass (curl_cffi)
    - Rate limiting
    - Automatic retries with exponential backoff
    - Proxy support
    - Thread-safe operations
    """
    
    def __init__(
        self,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
        proxy_url: Optional[Union[str, List[str]]] = None,
    ):
        """
        Initialize HTTP client.
        
        Args:
            delay_seconds: Delay between requests for rate limiting
            max_retries: Maximum retry attempts for failed requests
            timeout: Request timeout in seconds
            proxy_url: Optional proxy URL(s). Can be:
                - Single URL: "http://user:pass@host:port"
                - List of URLs for rotation: ["http://proxy1:port", "http://proxy2:port"]
        """
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Thread-safety locks
        self._lock = threading.Lock()
        
        # Setup proxy rotation
        self._proxy_list: List[str] = []
        self._proxy_index: int = 0
        
        if proxy_url:
            if isinstance(proxy_url, list):
                self._proxy_list = proxy_url
                logger.info(f"Proxy rotation enabled with {len(proxy_url)} proxies")
            else:
                self._proxy_list = [proxy_url]
        
        # For backwards compatibility
        self.proxy_url = proxy_url if isinstance(proxy_url, str) else (self._proxy_list[0] if self._proxy_list else None)
        self.proxies: Optional[Dict[str, str]] = None
        
        # Create session with Chrome fingerprint
        self.session = curl_requests.Session(impersonate="chrome")
        self._last_request_time: float = 0
    
    def _get_proxy(self) -> Optional[Dict[str, str]]:
        """Get the next proxy in rotation, or None if no proxies configured. Thread-safe."""
        if not self._proxy_list:
            return None
        
        with self._lock:
            # Round-robin rotation
            proxy = self._proxy_list[self._proxy_index]
            self._proxy_index = (self._proxy_index + 1) % len(self._proxy_list)
        
        return {"http": proxy, "https": proxy}
    
    def _rate_limit(self) -> None:
        """Apply rate limiting between requests. Thread-safe."""
        with self._lock:
            elapsed = time.time() - self._last_request_time
            if elapsed < self.delay_seconds:
                time.sleep(self.delay_seconds - elapsed)
            self._last_request_time = time.time()
    
    def _sanitize_proxy_for_log(self, proxy_url: Optional[str]) -> Optional[str]:
        """Sanitize proxy URL for logging, hiding credentials."""
        if not proxy_url:
            return None
        
        # Hide user:pass from proxy URL
        import re
        sanitized = re.sub(r'://[^:]+:[^@]+@', '://***:***@', proxy_url)
        # Truncate if still too long
        if len(sanitized) > 40:
            sanitized = sanitized[:40] + "..."
        return sanitized
    
    def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> curl_requests.Response:
        """
        Make a rate-limited request with automatic retries.
        
        Args:
            url: Request URL
            method: HTTP method (GET, POST, etc.)
            headers: Optional additional headers
            **kwargs: Additional arguments passed to curl_cffi
            
        Returns:
            Response object
            
        Raises:
            IdealoBlockedError: If blocked by anti-bot (403)
            RateLimitError: If rate limited (429)
            ProductNotFoundError: If product not found (404)
            IdealoError: For other errors
        """
        self._rate_limit()
        
        # Rotate User-Agent for each request
        merged_headers = {
            **DEFAULT_HEADERS,
            "User-Agent": get_random_user_agent(),
            **(headers or {})
        }
        
        # Get proxy (with rotation if multiple configured)
        current_proxy = self._get_proxy()
        proxy_str = list(current_proxy.values())[0] if current_proxy else None
        
        for attempt in range(self.max_retries):
            try:
                # Generate unique request ID for tracing
                request_id = str(uuid.uuid4())[:8]
                
                # Set logging context for this request
                set_request_context(
                    url=url[:80] + "..." if len(url) > 80 else url,
                    proxy=self._sanitize_proxy_for_log(proxy_str),
                    attempt=f"{attempt + 1}/{self.max_retries}",
                    request_id=request_id,
                )
                
                logger.debug(f"Making request [{request_id}]")
                
                response = self.session.request(
                    method=method,
                    url=url,
                    headers=merged_headers,
                    timeout=self.timeout,
                    proxies=current_proxy,
                    **kwargs,
                )
                
                # Check for blocking/errors
                if response.status_code == 403:
                    raise IdealoBlockedError("Access forbidden (403)", 403)
                elif response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    raise RateLimitError(retry_after)
                elif response.status_code == 404:
                    raise ProductNotFoundError(url=url)
                elif response.status_code >= 500:
                    if attempt < self.max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    raise IdealoError(f"Server error: {response.status_code}")
                
                return response
                
            except (IdealoBlockedError, ProductNotFoundError, RateLimitError):
                raise
            except Exception as e:
                if attempt < self.max_retries - 1:
                    logger.warning(f"Request failed, retrying: {e}")
                    time.sleep(2 ** attempt)
                    continue
                raise IdealoError(f"Request failed after {self.max_retries} attempts: {e}")
        
        raise IdealoError("Max retries exceeded")
    
    def get(self, url: str, **kwargs) -> curl_requests.Response:
        """Convenience method for GET requests."""
        return self.request(url, method="GET", **kwargs)
    
    def close(self) -> None:
        """Close the session."""
        if self.session:
            self.session.close()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class AsyncHttpClient:
    """
    Async HTTP client for Idealo with:
    - TLS fingerprint bypass (curl_cffi AsyncSession)
    - Rate limiting with semaphore
    - Automatic retries with exponential backoff
    - Proxy support
    
    This mirrors the sync HttpClient but uses async/await.
    """
    
    def __init__(
        self,
        delay_seconds: float = DEFAULT_DELAY_SECONDS,
        max_retries: int = DEFAULT_MAX_RETRIES,
        timeout: int = DEFAULT_TIMEOUT,
        max_concurrent: int = 5,
        proxy_url: Optional[Union[str, List[str]]] = None,
    ):
        """
        Initialize async HTTP client.
        
        Args:
            delay_seconds: Delay between requests for rate limiting
            max_retries: Maximum retry attempts for failed requests
            timeout: Request timeout in seconds
            max_concurrent: Maximum concurrent requests (semaphore limit)
            proxy_url: Optional proxy URL(s)
        """
        self.delay_seconds = delay_seconds
        self.max_retries = max_retries
        self.timeout = timeout
        self.max_concurrent = max_concurrent
        
        # Setup proxy rotation
        self._proxy_list: List[str] = []
        self._proxy_index: int = 0
        
        if proxy_url:
            if isinstance(proxy_url, list):
                self._proxy_list = proxy_url
                logger.info(f"Async proxy rotation enabled with {len(proxy_url)} proxies")
            else:
                self._proxy_list = [proxy_url]
        
        self.proxy_url = proxy_url if isinstance(proxy_url, str) else (self._proxy_list[0] if self._proxy_list else None)
        
        # Session created lazily in __aenter__
        self._session: Optional['curl_requests.AsyncSession'] = None
        self._semaphore: Optional['asyncio.Semaphore'] = None
        self._last_request_time: float = 0
        self._lock: Optional['asyncio.Lock'] = None
    
    def _get_proxy(self) -> Optional[Dict[str, str]]:
        """Get the next proxy in rotation."""
        if not self._proxy_list:
            return None
        
        proxy = self._proxy_list[self._proxy_index]
        self._proxy_index = (self._proxy_index + 1) % len(self._proxy_list)
        
        return {"http": proxy, "https": proxy}
    
    def _sanitize_proxy_for_log(self, proxy_url: Optional[str]) -> Optional[str]:
        """Sanitize proxy URL for logging, hiding credentials."""
        if not proxy_url:
            return None
        
        import re
        sanitized = re.sub(r'://[^:]+:[^@]+@', '://***:***@', proxy_url)
        if len(sanitized) > 40:
            sanitized = sanitized[:40] + "..."
        return sanitized
    
    async def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        import asyncio
        loop = asyncio.get_running_loop()
        
        async with self._lock:
            elapsed = loop.time() - self._last_request_time
            if elapsed < self.delay_seconds:
                await asyncio.sleep(self.delay_seconds - elapsed)
            self._last_request_time = loop.time()
    
    async def request(
        self,
        url: str,
        method: str = "GET",
        headers: Optional[Dict[str, str]] = None,
        **kwargs
    ) -> 'curl_requests.Response':
        """
        Make a rate-limited async request with automatic retries.
        
        Args:
            url: Request URL
            method: HTTP method
            headers: Optional additional headers
            **kwargs: Additional arguments
            
        Returns:
            Response object
        """
        import asyncio
        
        async with self._semaphore:
            await self._rate_limit()
            
            merged_headers = {
                **DEFAULT_HEADERS,
                "User-Agent": get_random_user_agent(),
                **(headers or {})
            }
            
            current_proxy = self._get_proxy()
            proxy_str = list(current_proxy.values())[0] if current_proxy else None
            
            for attempt in range(self.max_retries):
                try:
                    request_id = str(uuid.uuid4())[:8]
                    
                    set_request_context(
                        url=url[:80] + "..." if len(url) > 80 else url,
                        proxy=self._sanitize_proxy_for_log(proxy_str),
                        attempt=f"{attempt + 1}/{self.max_retries}",
                        request_id=request_id,
                    )
                    
                    logger.debug(f"Making async request [{request_id}]")
                    
                    response = await self._session.request(
                        method=method,
                        url=url,
                        headers=merged_headers,
                        timeout=self.timeout,
                        proxies=current_proxy,
                        **kwargs,
                    )
                    
                    # Check for blocking/errors
                    if response.status_code == 403:
                        raise IdealoBlockedError("Access forbidden (403)", 403)
                    elif response.status_code == 429:
                        retry_after = int(response.headers.get("Retry-After", 60))
                        raise RateLimitError(retry_after)
                    elif response.status_code == 404:
                        raise ProductNotFoundError(url=url)
                    elif response.status_code >= 500:
                        if attempt < self.max_retries - 1:
                            await asyncio.sleep(2 ** attempt)
                            continue
                        raise IdealoError(f"Server error: {response.status_code}")
                    
                    return response
                    
                except (IdealoBlockedError, ProductNotFoundError, RateLimitError):
                    raise
                except Exception as e:
                    if attempt < self.max_retries - 1:
                        logger.warning(f"Async request failed, retrying: {e}")
                        await asyncio.sleep(2 ** attempt)
                        continue
                    raise IdealoError(f"Request failed after {self.max_retries} attempts: {e}")
            
            raise IdealoError("Max retries exceeded")
    
    async def get(self, url: str, **kwargs) -> 'curl_requests.Response':
        """Convenience method for async GET requests."""
        return await self.request(url, method="GET", **kwargs)
    
    async def close(self) -> None:
        """Close the async session."""
        if self._session:
            await self._session.close()
    
    async def __aenter__(self):
        import asyncio
        from curl_cffi.requests import AsyncSession
        
        self._session = AsyncSession(
            impersonate="chrome",
            timeout=self.timeout,
            proxies=self._get_proxy(),
        )
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._lock = asyncio.Lock()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

