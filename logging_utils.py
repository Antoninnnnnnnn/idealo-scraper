"""Structured logging utilities for Idealo Scraper."""
import logging
import json
from typing import Optional, Any, Dict
from functools import wraps
from contextvars import ContextVar

# Context variables for structured logging
_request_context: ContextVar[Dict[str, Any]] = ContextVar('request_context', default={})


class StructuredLogAdapter(logging.LoggerAdapter):
    """
    Log adapter that adds contextual information to log messages.
    
    Adds product_id, proxy, country, etc. to all log messages for better debugging.
    """
    
    def process(self, msg: str, kwargs: Dict[str, Any]) -> tuple:
        """Add context to log message."""
        extra = kwargs.get('extra', {})
        
        # Merge with context from ContextVar
        context = _request_context.get()
        if context:
            extra.update(context)
        
        # Merge with adapter's extra
        if self.extra:
            extra.update(self.extra)
        
        kwargs['extra'] = extra
        
        # Format message with context if present
        if extra:
            context_str = ' '.join(f'[{k}={v}]' for k, v in extra.items() if v is not None)
            if context_str:
                msg = f"{context_str} {msg}"
        
        return msg, kwargs


def get_logger(name: str, **default_context) -> StructuredLogAdapter:
    """
    Get a structured logger with optional default context.
    
    Args:
        name: Logger name (usually __name__)
        **default_context: Default context to include in all messages
        
    Returns:
        StructuredLogAdapter with context support
    """
    logger = logging.getLogger(name)
    return StructuredLogAdapter(logger, default_context)


def set_request_context(**context) -> None:
    """
    Set context for the current request/operation.
    
    This context will be included in all log messages until cleared.
    
    Args:
        **context: Key-value pairs to add to log context
    """
    current = _request_context.get().copy()
    current.update(context)
    _request_context.set(current)


def clear_request_context() -> None:
    """Clear the current request context."""
    _request_context.set({})


def with_context(**context):
    """
    Decorator to set logging context for a function.
    
    Usage:
        @with_context(operation="search")
        def search(query):
            logger.info("Searching...")  # Will include [operation=search]
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            set_request_context(**context)
            try:
                return func(*args, **kwargs)
            finally:
                # Restore previous context (or clear if none)
                for key in context:
                    current = _request_context.get().copy()
                    current.pop(key, None)
                    _request_context.set(current)
        return wrapper
    return decorator


def configure_logging(
    level: int = logging.INFO,
    format_string: Optional[str] = None,
    json_output: bool = False,
) -> None:
    """
    Configure logging for the idealo_scraper package.
    
    Args:
        level: Logging level (default: INFO)
        format_string: Custom format string
        json_output: If True, output logs as JSON
    """
    if format_string is None:
        if json_output:
            format_string = '{"time": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}'
        else:
            format_string = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    logging.basicConfig(
        level=level,
        format=format_string,
        datefmt='%Y-%m-%d %H:%M:%S',
    )
    
    # Set level for idealo_scraper package
    logging.getLogger('idealo_scraper').setLevel(level)
