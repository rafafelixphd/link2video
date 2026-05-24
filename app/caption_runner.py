"""Background caption runner — same pattern as AudioRunner and TranscribeRunner."""
import threading
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from link2video.auto.caption import CaptionProcessor


class CaptionRunner:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self._ollama_url = ollama_url
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(
        self,
        video_path: str,
        interval_seconds: float,
        sequence_length: int,
        model: str,
        additional_query: str,
        context_sections: List[str],
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[run_id] = {"status": "pending", "result": None, "error": None}
        t = threading.Thread(
            target=self._run,
            args=(run_id, video_path, interval_seconds, sequence_length,
                  model, additional_query, context_sections),
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

    def _run(
        self,
        run_id: str,
        video_path: str,
        interval_seconds: float,
        sequence_length: int,
        model: str,
        additional_query: str,
        context_sections: List[str],
    ) -> None:
        with self._lock:
            if run_id not in self._runs:
                return
            self._runs[run_id]["status"] = "running"
        try:
            result = self._caption(video_path, interval_seconds, sequence_length,
                                   model, additional_query, context_sections)
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

    def _caption(
        self,
        video_path: str,
        interval_seconds: float,
        sequence_length: int,
        model: str,
        additional_query: str,
        context_sections: List[str],
    ) -> dict:
        processor = CaptionProcessor(ollama_url=self._ollama_url)
        processor.caption(
            video_path=video_path,
            interval_seconds=interval_seconds,
            sequence_length=sequence_length,
            model=model,
            additional_query=additional_query,
            context_sections=context_sections,
        )
        return {"yaml_path": str(Path(video_path).with_suffix(".yaml"))}
