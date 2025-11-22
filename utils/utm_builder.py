"""
UTM Parameter Builder for Traffic Attribution
Generates trackable links for Reddit content to measure ROI
"""
from urllib.parse import urlencode, urlparse, parse_qs, urlunparse
import logging

logger = logging.getLogger(__name__)

def build_utm_link(
    base_url: str,
    client_id: str,
    campaign: str = "reddit_echomind",
    medium: str = "social",
    content: str = None
) -> str:
    """
    Build URL with UTM parameters for traffic attribution
    
    Args:
        base_url: Client's website URL
        client_id: Client UUID for tracking
        campaign: Campaign name (default: reddit_echomind)
        medium: Traffic medium (default: social)
        content: Specific content identifier (post_id, subreddit, etc.)
    
    Returns:
        URL with UTM parameters appended
    
    Example:
        Input: https://example.com
        Output: https://example.com?utm_source=reddit&utm_medium=social&utm_campaign=reddit_echomind&utm_content=askreddit_post123
    """
    try:
        # Parse the base URL
        parsed = urlparse(base_url)
        
        # Build UTM parameters
        utm_params = {
            'utm_source': 'reddit',
            'utm_medium': medium,
            'utm_campaign': campaign,
            'utm_term': client_id[:8],  # Short client ID for tracking
        }
        
        if content:
            utm_params['utm_content'] = content
        
        # Merge with existing query parameters
        existing_params = parse_qs(parsed.query)
        for key, value in existing_params.items():
            if key not in utm_params:
                utm_params[key] = value[0] if isinstance(value, list) else value
        
        # Build new query string
        new_query = urlencode(utm_params)
        
        # Reconstruct URL
        new_url = urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))
        
        logger.debug(f"Built UTM link: {new_url}")
        return new_url
        
    except Exception as e:
        logger.error(f"Error building UTM link: {e}")
        return base_url  # Return original URL if something fails

def inject_link_naturally(
    content: str,
    website_url: str,
    client_id: str,
    subreddit: str,
    max_links: int = 1
) -> str:
    """
    Inject trackable link naturally into generated content
    
    Args:
        content: Generated Reddit content
        website_url: Client's website
        client_id: Client UUID
        subreddit: Target subreddit
        max_links: Maximum number of links to inject (default: 1)
    
    Returns:
        Content with UTM-tracked link injected naturally
    """
    try:
        # Build UTM link
        tracked_url = build_utm_link(
            base_url=website_url,
            client_id=client_id,
            content=f"{subreddit}_organic"
        )
        
        # Add link naturally at the end if not too spammy
        # Only add if content is substantial (> 100 chars) and doesn't already have a link
        if len(content) > 100 and 'http' not in content.lower():
            # Add subtle, helpful link
            content += f"\n\n^(More info: {tracked_url})"
            logger.info(f"✅ Injected tracked link into content")
        else:
            logger.debug("Skipped link injection (content too short or already has link)")
        
        return content
        
    except Exception as e:
        logger.error(f"Error injecting link: {e}")
        return content  # Return original content if something fails
