"""Custom exceptions for Idealo Scraper."""


class IdealoError(Exception):
    """Base exception for Idealo scraper errors."""
    pass


class IdealoBlockedError(IdealoError):
    """Raised when request is blocked by anti-bot protection."""
    
    def __init__(self, message: str = "Request blocked by Idealo anti-bot", status_code: int = None):
        super().__init__(message)
        self.status_code = status_code


class ProductNotFoundError(IdealoError):
    """Raised when product is not found."""
    
    def __init__(self, product_id: str = None, url: str = None):
        if product_id:
            message = f"Product not found: {product_id}"
        elif url:
            message = f"Product not found at URL: {url}"
        else:
            message = "Product not found"
        super().__init__(message)
        self.product_id = product_id
        self.url = url


class RateLimitError(IdealoError):
    """Raised when rate limit is hit (HTTP 429)."""
    
    def __init__(self, retry_after: int = None):
        message = "Rate limit exceeded"
        if retry_after:
            message += f", retry after {retry_after} seconds"
        super().__init__(message)
        self.retry_after = retry_after


class ParseError(IdealoError):
    """Raised when HTML/JSON parsing fails."""
    
    def __init__(self, message: str = "Failed to parse response", raw_content: str = None):
        super().__init__(message)
        self.raw_content = raw_content[:500] if raw_content else None
