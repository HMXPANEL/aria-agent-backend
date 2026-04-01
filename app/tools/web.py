import httpx
from bs4 import BeautifulSoup
from app.tools.registry import tool_registry
from app.utils.logger import logger

@tool_registry.register(
    name="web_search",
    description="Search the web for information using a search engine."
)
async def web_search(query: str) -> str:
    """
    Search the web for information.
    """
    logger.info(f"Searching web for: {query}")
    # Mock search for now, can be replaced with actual search API
    return f"Search results for '{query}': [Result 1, Result 2, Result 3]"

@tool_registry.register(
    name="web_scrape",
    description="Scrape content from a given URL."
)
async def web_scrape(url: str) -> str:
    """
    Scrape content from a URL.
    """
    logger.info(f"Scraping URL: {url}")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url, timeout=10.0)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, 'html.parser')
            # Extract text content
            for script in soup(["script", "style"]):
                script.decompose()
            text = soup.get_text()
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text = '\n'.join(chunk for chunk in chunks if chunk)
            return text[:2000] # Limit output
        except Exception as e:
            logger.error(f"Error scraping {url}: {e}")
            return f"Error scraping {url}: {e}"
