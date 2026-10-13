import asyncio
import logging
from typing import Dict
from .ffmpeg_muxer import download_and_mux

logger = logging.getLogger(__name__)

from .m3u8_parser import parse_master_playlist

class DownloadTask:
    def __init__(self, task_id: str, m3u8_url: str, output_path: str, format: str, quality: str):
        self.task_id = task_id
        self.master_m3u8_url = m3u8_url
        self.output_path = output_path
        self.format = format
        self.quality = quality

        self.stream_url = None
        self.status = "pending"
        self.progress = 0.0
        self.speed = "0x"
        self.eta = "N/A"
        self.process = None
        self.task = None

    def cancel(self):
        if self.process:
            self.process.terminate()
        if self.task:
            self.task.cancel()
        self.status = "cancelled"

class DownloadManager:
    def __init__(self):
        self.tasks: Dict[str, DownloadTask] = {}
        self.websockets = set()

    async def broadcast_progress(self):
        import json
        if not self.websockets:
            return
        message = json.dumps({
            task_id: {
                "status": task.status,
                "progress": task.progress,
                "speed": task.speed,
                "eta": task.eta
            } for task_id, task in self.tasks.items()
        })
        for ws in list(self.websockets):
            try:
                await ws.send_text(message)
            except Exception:
                self.websockets.remove(ws)

    def add_task(self, task_id: str, m3u8_url: str, output_path: str, format: str, quality: str):
        task = DownloadTask(task_id, m3u8_url, output_path, format, quality)
        self.tasks[task_id] = task
        task.task = asyncio.create_task(self._run_task(task))
        return task

    def get_task(self, task_id: str) -> DownloadTask | None:
        return self.tasks.get(task_id)

    async def _run_task(self, task: DownloadTask):
        task.status = "preparing"
        await self.broadcast_progress()

        try:
            # Resolve the correct m3u8 stream based on quality
            playlist_info = parse_master_playlist(task.master_m3u8_url)

            selected_url = task.master_m3u8_url # fallback

            if playlist_info["resolutions"]:
                if task.quality == "best":
                    selected_url = playlist_info["resolutions"][0]["url"]
                else:
                    target_height = int(task.quality.replace("p", "")) if "p" in task.quality else None
                    # Find exact or fallback to best
                    matched = next((r for r in playlist_info["resolutions"] if r["height"] == target_height), None)
                    if matched:
                        selected_url = matched["url"]
                    else:
                        selected_url = playlist_info["resolutions"][0]["url"]

            # Need absolute URL if relative
            import urllib.parse
            task.stream_url = urllib.parse.urljoin(task.master_m3u8_url, selected_url)

            task.status = "downloading"
            await download_and_mux(task, self.broadcast_progress)
            task.status = "completed"
            task.progress = 100.0
        except asyncio.CancelledError:
            task.status = "cancelled"
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            task.status = "failed"
        finally:
            await self.broadcast_progress()

download_manager = DownloadManager()
