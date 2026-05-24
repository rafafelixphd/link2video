"""Background audio extraction runner — same pattern as DownloadRunner."""
import contextlib
import json
import subprocess
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

from link2video.auto.extract_audio import ExtractAudioProcessor
from link2video.metadata_manager import MetadataManager


class AudioRunner:
    def __init__(self) -> None:
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, video_path: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[run_id] = {"status": "pending", "result": None, "error": None}
        t = threading.Thread(
            target=self._run,
            args=(run_id, video_path),
            daemon=True,
        )
        t.start()
        return run_id

    def get(self, run_id: str) -> Optional[dict]:
        with self._lock:
            entry = self._runs.get(run_id)
            return dict(entry) if entry else None

    def clear(self, run_id: str) -> None:
        with self._lock:
            self._runs.pop(run_id, None)

    def _run(self, run_id: str, video_path: str) -> None:
        with self._lock:
            if run_id not in self._runs:
                return
            self._runs[run_id]["status"] = "running"
        try:
            result = self._extract(video_path)
            with self._lock:
                if run_id not in self._runs:
                    return
                self._runs[run_id]["status"] = "completed"
                self._runs[run_id]["result"] = result
        except Exception as exc:
            with self._lock:
                if run_id not in self._runs:
                    return
                self._runs[run_id]["status"] = "failed"
                self._runs[run_id]["error"] = str(exc)

    def _extract(self, video_path: str) -> dict:
        """
        Extract audio to {video_dir}/{stem}.mp3 alongside the video.
        Uses ExtractAudioProcessor then moves the file from the namespace subdir.
        """
        video = Path(video_path)
        video_dir = video.parent
        stem = video.stem

        processor = ExtractAudioProcessor()
        result = processor.extract(
            input_file=video_path,
            output_dir=str(video_dir),
            namespace=stem,
            format="mp3",
        )
        # processor writes to {video_dir}/{stem}/{stem}.mp3
        src_mp3 = Path(result.audio_path)
        dst_mp3 = video_dir / f"{stem}.mp3"
        src_mp3.rename(dst_mp3)

        # Remove the processor's per-namespace YAML (we write our own unified YAML)
        src_yaml = Path(result.metadata_path)
        if src_yaml.exists():
            src_yaml.unlink()
        # Remove the now-empty namespace subdir
        with contextlib.suppress(OSError):
            src_mp3.parent.rmdir()

        probe = self._probe_audio(str(dst_mp3))

        MetadataManager().update(video_path, "link2video/auto/extract", {
            "format": "mp3",
            "duration": round(result.duration, 3),
            "sample_rate": probe["sample_rate"],
            "channels": probe["channels"],
        })

        return {"mp3_path": str(dst_mp3)}

    def _probe_audio(self, path: str) -> dict:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate,channels",
                "-of", "json",
                path,
            ],
            capture_output=True, text=True, check=True,
        )
        stream = json.loads(out.stdout).get("streams", [{}])[0]
        return {
            "sample_rate": int(stream.get("sample_rate", 0)),
            "channels": int(stream.get("channels", 1)),
        }
