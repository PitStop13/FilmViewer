import m3u8
import requests
import logging
from .domain_manager import get_headers

logger = logging.getLogger(__name__)

def parse_master_playlist(url: str) -> dict:
    try:
        response = requests.get(url, headers=get_headers(), timeout=10)
        response.raise_for_status()

        playlist = m3u8.loads(response.text, uri=url)

        resolutions = []
        for p in playlist.playlists:
            if p.stream_info.resolution:
                width, height = p.stream_info.resolution
                resolutions.append({
                    "width": width,
                    "height": height,
                    "bandwidth": p.stream_info.bandwidth,
                    "url": p.uri
                })

        # Handle audio tracks if present
        audio_tracks = []
        if playlist.media:
            for media in playlist.media:
                if media.type == "AUDIO":
                    audio_tracks.append({
                        "group_id": media.group_id,
                        "name": media.name,
                        "language": media.language,
                        "url": media.uri
                    })

        # Handle subtitles
        subtitles = []
        if playlist.media:
            for media in playlist.media:
                if media.type == "SUBTITLES":
                    subtitles.append({
                        "group_id": media.group_id,
                        "name": media.name,
                        "language": media.language,
                        "url": media.uri
                    })

        return {
            "resolutions": sorted(resolutions, key=lambda x: x["height"], reverse=True),
            "audio_tracks": audio_tracks,
            "subtitles": subtitles
        }
    except Exception as e:
        logger.error(f"Failed to parse master playlist {url}: {e}")
        return {"resolutions": [], "audio_tracks": [], "subtitles": []}
