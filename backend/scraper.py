import logging
import requests
from bs4 import BeautifulSoup
from .domain_manager import get_headers, get_current_domain

logger = logging.getLogger(__name__)

def search_title(query: str) -> list[dict]:
    domain = get_current_domain()
    if not domain:
        raise ValueError("No working domain found")

    url = f"https://{domain}/api/search?q={query}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])
    except Exception as e:
        logger.error(f"Failed to search for '{query}': {e}")
        return []

def get_title_details(title_id: int) -> dict:
    domain = get_current_domain()
    if not domain:
        raise ValueError("No working domain found")

    url = f"https://{domain}/titles/{title_id}"
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")

        # We need to extract the inertia page data
        inertia_div = soup.find("div", id="app")
        if not inertia_div:
            return {}

        import json
        page_data = json.loads(inertia_div.get("data-page", "{}"))
        return page_data.get("props", {}).get("title", {})
    except Exception as e:
        logger.error(f"Failed to fetch details for title {title_id}: {e}")
        return {}

def extract_iframe_url(title_id: int, episode_id: int | None = None) -> str | None:
    # Get details and extract iframe
    # The actual implementation depends on StreamingCommunity's current frontend structure
    # For a simplified proxy, we'll return a stub URL or try to fetch it if possible
    domain = get_current_domain()
    if not domain:
        return None

    url = f"https://{domain}/iframe/{title_id}"
    if episode_id:
        url += f"?episode_id={episode_id}"

    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()

        # Typically the actual streaming iframe contains an m3u8 playlist URL
        soup = BeautifulSoup(response.text, "lxml")

        # Scrape master m3u8 url from the script tag containing player config
        for script in soup.find_all("script"):
            if "master.m3u8" in script.text:
                import re
                match = re.search(r'url:\s*"(https://[^"]+\.m3u8[^"]*)"', script.text)
                if match:
                    return match.group(1).replace("\\/", "/")

    except Exception as e:
        logger.error(f"Failed to extract iframe for title {title_id}: {e}")
        return None
    return None
