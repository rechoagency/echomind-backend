"""
Retry decorator with exponential backoff for robust error handling.
Use this for all external API calls (OpenAI, Reddit, Supabase).
"""
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging
from typing import Type, Tuple

logger = logging.getLogger(__name__)

# Common retry decorator for external API calls
def retry_on_api_error(
    max_attempts: int = 3,
    min_wait: int = 2,
    max_wait: int = 10,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Retry decorator with exponential backoff for API calls.
    
    Args:
        max_attempts: Maximum number of retry attempts (default: 3)
        min_wait: Minimum wait time in seconds (default: 2)
        max_wait: Maximum wait time in seconds (default: 10)
        exceptions: Tuple of exception types to retry on (default: all exceptions)
    
    Returns:
        Decorated function with retry logic
    
    Usage:
        @retry_on_api_error(max_attempts=5, exceptions=(ConnectionError, TimeoutError))
        def call_external_api():
            response = requests.get(...)
            return response
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=min_wait, max=max_wait),
        retry=retry_if_exception_type(exceptions),
        before_sleep=before_sleep_log(logger, logging.WARNING),
        reraise=True
    )


# Specific retry configurations for different services

def retry_on_openai_error(max_attempts: int = 3):
    """Retry decorator specifically for OpenAI API calls."""
    from openai import APIError, APIConnectionError, RateLimitError, Timeout
    
    return retry_on_api_error(
        max_attempts=max_attempts,
        min_wait=2,
        max_wait=30,
        exceptions=(APIError, APIConnectionError, RateLimitError, Timeout)
    )


def retry_on_reddit_error(max_attempts: int = 3):
    """Retry decorator specifically for Reddit API calls."""
    from prawcore.exceptions import RequestException, ResponseException, ServerError
    
    return retry_on_api_error(
        max_attempts=max_attempts,
        min_wait=5,
        max_wait=60,  # Reddit rate limits can be aggressive
        exceptions=(RequestException, ResponseException, ServerError)
    )


def retry_on_supabase_error(max_attempts: int = 3):
    """Retry decorator specifically for Supabase calls."""
    import requests
    
    return retry_on_api_error(
        max_attempts=max_attempts,
        min_wait=1,
        max_wait=10,
        exceptions=(requests.exceptions.RequestException, ConnectionError, TimeoutError)
    )
