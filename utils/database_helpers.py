"""
Database helper utilities for safe, performant queries.
Use these instead of raw Supabase queries to avoid common pitfalls.
"""
import logging
from typing import Dict, List, Any, Optional
from supabase import Client

logger = logging.getLogger(__name__)

# Default pagination limits
DEFAULT_LIMIT = 100
MAX_LIMIT = 1000


def safe_select(
    client: Client,
    table: str,
    columns: str = "*",
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[str] = None,
    desc: bool = False,
    limit: int = DEFAULT_LIMIT,
    offset: int = 0
) -> List[Dict]:
    """
    Safely query Supabase with automatic pagination and error handling.
    
    Args:
        client: Supabase client instance
        table: Table name
        columns: Columns to select (default: "*")
        filters: Dict of column: value filters to apply
        order_by: Column to order by
        desc: Order descending if True
        limit: Maximum rows to return (default: 100, max: 1000)
        offset: Number of rows to skip
        
    Returns:
        List of result dictionaries
        
    Example:
        results = safe_select(
            supabase,
            "opportunities",
            filters={"client_id": "abc123"},
            order_by="created_at",
            desc=True,
            limit=50
        )
    """
    try:
        # Enforce maximum limit
        if limit > MAX_LIMIT:
            logger.warning(f"Limit {limit} exceeds maximum {MAX_LIMIT}, capping")
            limit = MAX_LIMIT
        
        # Build query
        query = client.table(table).select(columns)
        
        # Apply filters
        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)
        
        # Apply ordering
        if order_by:
            query = query.order(order_by, desc=desc)
        
        # Apply pagination
        query = query.limit(limit).offset(offset)
        
        # Execute
        response = query.execute()
        return response.data or []
        
    except Exception as e:
        logger.error(f"Error in safe_select from {table}: {e}")
        return []


def paginated_select(
    client: Client,
    table: str,
    columns: str = "*",
    filters: Optional[Dict[str, Any]] = None,
    order_by: Optional[str] = None,
    desc: bool = False,
    page_size: int = 100
) -> List[Dict]:
    """
    Query ALL rows from a table with automatic pagination.
    Use carefully - only for batch processing, not user-facing queries.
    
    Args:
        client: Supabase client instance
        table: Table name
        columns: Columns to select
        filters: Dict of filters
        order_by: Column to order by
        desc: Order descending
        page_size: Rows per page (default: 100)
        
    Yields:
        Batches of results
        
    Example:
        for batch in paginated_select(supabase, "opportunities", page_size=500):
            process_batch(batch)
    """
    offset = 0
    all_results = []
    
    while True:
        batch = safe_select(
            client,
            table,
            columns=columns,
            filters=filters,
            order_by=order_by,
            desc=desc,
            limit=page_size,
            offset=offset
        )
        
        if not batch:
            break
        
        all_results.extend(batch)
        offset += page_size
        
        # Safety: stop if we've fetched 10k+ rows
        if offset >= 10000:
            logger.warning(f"Fetched 10k+ rows from {table}, stopping pagination")
            break
        
        # If we got fewer results than page_size, we've reached the end
        if len(batch) < page_size:
            break
    
    return all_results


def count_rows(
    client: Client,
    table: str,
    filters: Optional[Dict[str, Any]] = None
) -> int:
    """
    Count rows in a table efficiently.
    
    Args:
        client: Supabase client
        table: Table name
        filters: Optional filters
        
    Returns:
        Row count
    """
    try:
        query = client.table(table).select("id", count="exact")
        
        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)
        
        response = query.execute()
        return response.count or 0
        
    except Exception as e:
        logger.error(f"Error counting rows in {table}: {e}")
        return 0
