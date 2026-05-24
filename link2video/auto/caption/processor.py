# link2video/auto/caption/processor.py
import base64
import re
import subprocess
from pathlib import Path

import ollama


class CaptionProcessor:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self._client = ollama.Client(host=ollama_url)

    def _get_video_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())

    def _extract_frames(self, video_path: str, out_dir: str, interval_seconds: float) -> None:
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"fps=1/{interval_seconds}",
                "-q:v", "2",
                str(Path(out_dir) / "frame_%04d.jpg"),
            ],
            check=True, capture_output=True,
        )

    def _encode_frame(self, frame_path: str) -> str:
        with open(frame_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _call_ollama(self, model: str, prompt: str, images: list | None = None) -> str:
        kwargs = {"model": model, "prompt": prompt}
        if images:
            kwargs["images"] = images
        response = self._client.generate(**kwargs)
        return response["response"]

    def _parse_frame_descriptions(self, text: str, expected_count: int) -> list:
        pattern = re.compile(r"Frame\s+\d+:\s*(.+?)(?=Frame\s+\d+:|$)", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        descriptions = [m.strip() for m in matches]
        while len(descriptions) < expected_count:
            descriptions.append("[parse error]")
        return descriptions[:expected_count]
