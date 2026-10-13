import asyncio
import logging
import re
import os

logger = logging.getLogger(__name__)

async def download_and_mux(task, progress_callback):
    """
    Downloads an m3u8 stream using ffmpeg and muxes it to the requested format.
    Updates the task's progress and process reference.
    """
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(task.output_path), exist_ok=True)

    # Ensure proper extension based on format
    output_file = task.output_path
    if not output_file.endswith(f".{task.format}"):
        output_file += f".{task.format}"

    cmd = [
        "ffmpeg",
        "-y", # overwrite output
        "-i", task.stream_url,
        "-c", "copy", # Copy streams without re-encoding
        "-progress", "pipe:1",
        output_file
    ]

    logger.info(f"Starting ffmpeg for {task.task_id}: {' '.join(cmd)}")

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT
    )

    task.process = process

    # Simple regex to extract time/duration from ffmpeg output for progress
    # Ffmpeg outputs duration initially: Duration: 00:23:45.12
    # Then it outputs time periodically: time=00:10:00.00

    duration_secs = 0

    duration_re = re.compile(r"Duration: (\d+):(\d+):(\d+\.\d+)")
    time_re = re.compile(r"out_time=(\d+):(\d+):(\d+\.\d+)")
    time_re_alt = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    speed_re = re.compile(r"speed=\s*([\d.]+)x")

    try:
        while True:
            line = await process.stdout.readline()
            if not line:
                break

            line_str = line.decode("utf-8", errors="ignore").strip()

            if duration_secs == 0:
                match = duration_re.search(line_str)
                if match:
                    h, m, s = match.groups()
                    duration_secs = int(h)*3600 + int(m)*60 + float(s)

            # Extract speed
            smatch = speed_re.search(line_str)
            if smatch:
                task.speed = f"{smatch.group(1)}x"
                speed_val = float(smatch.group(1))
            else:
                speed_val = 1.0

            # Progress format 1 (from -progress)
            match = time_re.search(line_str)
            if not match:
                # Progress format 2 (from stderr)
                match = time_re_alt.search(line_str)

            if match and duration_secs > 0:
                h, m, s = match.groups()
                current_secs = int(h)*3600 + int(m)*60 + float(s)
                progress = min(100.0, max(0.0, (current_secs / duration_secs) * 100))
                task.progress = round(progress, 1)

                # Calculate ETA
                if speed_val > 0 and current_secs > 0:
                    remaining_secs = duration_secs - current_secs
                    eta_secs = remaining_secs / speed_val
                    if eta_secs < 60:
                        task.eta = f"{int(eta_secs)}s"
                    elif eta_secs < 3600:
                        task.eta = f"{int(eta_secs // 60)}m {int(eta_secs % 60)}s"
                    else:
                        task.eta = f"{int(eta_secs // 3600)}h {int((eta_secs % 3600) // 60)}m"

                await progress_callback()

    except asyncio.CancelledError:
        process.terminate()
        raise
    finally:
        await process.wait()
        if process.returncode != 0 and process.returncode != 255: # 255 is often returned on manual termination
            logger.error(f"Ffmpeg exited with code {process.returncode}")
            raise RuntimeError(f"Ffmpeg exited with code {process.returncode}")
