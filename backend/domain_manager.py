import asyncio
import logging
import re
import socket
import threading
import time
from urllib.parse import urlparse
import requests
from bs4 import BeautifulSoup
import ipaddress

logger = logging.getLogger(__name__)

CANDIDATES_URL = "https://telegra.ph/Link-Aggiornato-StreamingCommunity-09-29"
NAME_PATTERN = re.compile(r"^streaming(community|unity)[a-z0-9-]{0,12}$")
_HOST_RE = re.compile(r"^[a-z0-9.-]{4,253}$")
_LOCAL_SUFFIXES = (".local", ".internal", ".localhost", ".home", ".lan")
_MAX_CANDIDATES = 5
_MIN_CHECK_INTERVAL = 600

_lock = threading.Lock()
_current_domain = None
_last_check_at = None

def get_headers():
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    }

def get_current_domain():
    global _current_domain
    with _lock:
        return _current_domain

def set_current_domain(domain):
    global _current_domain
    with _lock:
        _current_domain = domain

def fetch_candidates(url: str | None = None) -> list[str]:
    target = url or CANDIDATES_URL
    try:
        response = requests.get(target, headers=get_headers(), timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        logger.error(f"Failed to fetch candidates from {target}: {e}")
        return []

    soup = BeautifulSoup(response.text, "lxml")
    hosts: list[str] = []
    for anchor in soup.find_all("a"):
        href = (anchor.get("href") or "").strip()
        if not href:
            continue
        parsed = urlparse(href)
        if parsed.scheme == "https" and parsed.netloc and parsed.netloc not in hosts:
            hosts.append(parsed.netloc)
        if len(hosts) >= _MAX_CANDIDATES:
            break
    return hosts

def _check_shape(host: str) -> str | None:
    if not host or not _HOST_RE.match(host):
        return "invalid shape"
    if host.endswith(_LOCAL_SUFFIXES) or host == "localhost":
        return "local name"
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        return "IP address"
    labels = host.split(".")
    if len(labels) == 3 and labels[0] == "www":
        labels = labels[1:]
    if len(labels) != 2:
        return "not a second-level domain"
    name = labels[0]
    if not NAME_PATTERN.match(name):
        return f"name '{name}' not recognized"
    return None

def _resolves_to_public(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except OSError as exc:
        logger.info(f"Candidate {host} does not resolve: {exc}")
        return False
    if not infos:
        return False
    for info in infos:
        try:
            address = ipaddress.ip_address(info[4][0])
        except ValueError:
            return False
        if (address.is_private or address.is_loopback or address.is_link_local
            or address.is_reserved or address.is_multicast or address.is_unspecified):
            return False
    return True

def is_plausible(host: str) -> tuple[bool, str]:
    reason = _check_shape(host)
    if reason:
        return False, reason
    if not _resolves_to_public(host):
        return False, "resolves to a non-public address"
    return True, ""

def get_domain_version(host: str) -> str | None:
    try:
        url = f"https://{host}/"
        response = requests.get(url, headers=get_headers(), timeout=10)
        soup = BeautifulSoup(response.text, "lxml")

        # In sc-downloader, they extract the version from the frontend assets
        # E.g., <script src="/js/app.js?id=..."></script>
        for script in soup.find_all("script"):
            src = script.get("src", "")
            if "app.js?id=" in src:
                return src.split("?id=")[1]
    except Exception as e:
        logger.info(f"Failed to verify version for {host}: {e}")
        return None
    return None

def verify(host: str) -> str | None:
    version = get_domain_version(host)
    if not version:
        logger.info(f"Candidate {host} failed verification: no version found")
        return None
    return version

def run_check(force: bool = False) -> dict:
    global _last_check_at
    current = get_current_domain()
    now = time.monotonic()

    if not force:
        with _lock:
            if _last_check_at is not None and now - _last_check_at < _MIN_CHECK_INTERVAL:
                return {"status": "skipped", "domain": current}

    with _lock:
        _last_check_at = now

    current_ok = False
    if current:
        current_ok = verify(current) is not None

    if current_ok and not force:
        return {"status": "working", "domain": current}

    candidates = fetch_candidates()
    for host in candidates:
        if host == current:
            continue
        ok, reason = is_plausible(host)
        if not ok:
            continue
        version = verify(host)
        if version is not None:
            logger.info(f"New source domain set to {host} (version {version})")
            set_current_domain(host)
            return {"status": "updated", "domain": host, "version": version}

    return {"status": "failed", "domain": current}

async def domain_watch_loop():
    while True:
        try:
            await asyncio.to_thread(run_check)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.exception("Domain check failed")
        await asyncio.sleep(3600) # Check every hour
