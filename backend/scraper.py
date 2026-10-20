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
    domain = get_current_domain()
    if not domain:
        return None

    paths = [f"/it/iframe/{title_id}", f"/iframe/{title_id}"]
    for path in paths:
        url = f"https://{domain}{path}"
        if episode_id:
            url += f"?episode_id={episode_id}"

        try:
            response = requests.get(url, headers=get_headers(), timeout=10)
            if not response.ok:
                continue

            soup = BeautifulSoup(response.text, "lxml")
            iframe = soup.find("iframe")
            if iframe and iframe.get("src"):
                embed_src = iframe.get("src")
                try:
                    req_embed = requests.get(
                        embed_src,
                        headers={"user-agent": get_headers()["User-Agent"], "referer": f"https://{domain}/"},
                        timeout=15,
                    )
                    if req_embed.ok:
                        import re
                        match = re.search(r'url:\s*["\'](https://[^"\']+playlist[^"\']*)["\']', req_embed.text)
                        if match:
                            return match.group(1).replace(r"\/", "/")
                except Exception:
                    pass

            for script in soup.find_all("script"):
                if "playlist" in script.text or "master.m3u8" in script.text:
                    import re
                    match = re.search(r'url:\s*["\'](https://[^"\']+)["\']', script.text)
                    if match:
                        return match.group(1).replace(r"\/", "/")
        except Exception as e:
            logger.error(f"Failed to extract iframe for title {title_id}: {e}")
    return None
