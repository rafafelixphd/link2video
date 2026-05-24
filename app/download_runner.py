"""Background download runner — single URL, in-memory state."""
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from link2video.platform_detector import detect_platform


class DownloadRunner:
    def __init__(self) -> None:
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(self, url: str, save_path: str, tags: List[str], comments: str) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[run_id] = {"status": "pending", "result": None, "error": None}
        t = threading.Thread(
            target=self._run,
            args=(run_id, url, save_path, tags, comments),
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

    def _run(self, run_id: str, url: str, save_path: str, tags: List[str], comments: str) -> None:
        with self._lock:
            if run_id not in self._runs:
                return
            self._runs[run_id]["status"] = "running"
        try:
            Path(save_path).expanduser().mkdir(parents=True, exist_ok=True)
            downloader = detect_platform(url)
            success, result = downloader.download(url, save_path, tags=tags, comments=comments)
            with self._lock:
                if run_id not in self._runs:
                    return
                if success:
                    self._runs[run_id]["status"] = "completed"
                    self._runs[run_id]["result"] = result
                else:
                    self._runs[run_id]["status"] = "failed"
                    self._runs[run_id]["error"] = result
        except Exception as exc:
            with self._lock:
                if run_id not in self._runs:
                    return
                self._runs[run_id]["status"] = "failed"
                self._runs[run_id]["error"] = str(exc)
