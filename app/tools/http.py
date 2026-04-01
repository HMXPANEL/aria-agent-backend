import requests
from typing import Dict, Any, Optional
from app.tools.registry import tool_registry
from app.utils.logger import logger

async def http_request(method: str, url: str, headers: Optional[Dict[str, str]] = None, data: Optional[Dict[str, Any]] = None, json: Optional[Dict[str, Any]] = None) -> str:
    """
    Perform an HTTP request.
    """
    logger.info(f"Performing HTTP {method} request to {url}")
    try:
        response = requests.request(method, url, headers=headers, data=data, json=json, timeout=10)
        response.raise_for_status()
        return response.text[:2000] # Limit response size
    except Exception as e:
        logger.error(f"Error performing HTTP request to {url}: {e}")
        return f"Error performing HTTP request to {url}: {str(e)}"

tool_registry.register("http_request", http_request)
