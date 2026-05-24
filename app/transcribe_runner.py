"""Background transcription runner — same pattern as DownloadRunner."""
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Dict, Optional

from link2video.auto.transcribe import TranscribeProcessor
from link2video.metadata_manager import MetadataManager


class TranscribeRunner:
    def __init__(self, audio_runner) -> None:
        self._audio_runner = audio_runner
        self._runs: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def start(
        self,
        video_path: str,
        model: str = "base",
        language: str = "en",
        device: str = "auto",
    ) -> str:
        run_id = uuid.uuid4().hex[:12]
        with self._lock:
            self._runs[run_id] = {"status": "pending", "result": None, "error": None}
        t = threading.Thread(
            target=self._run,
            args=(run_id, video_path, model, language, device),
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
        model: str,
        language: str,
        device: str,
    ) -> None:
        with self._lock:
            if run_id not in self._runs:
                return
            self._runs[run_id]["status"] = "running"
        try:
            result = self._transcribe(video_path, model, language, device)
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

    def _transcribe(
        self,
        video_path: str,
        model: str,
        language: str,
        device: str,
    ) -> dict:
        video = Path(video_path)
        mp3_path = video.with_suffix(".mp3")

        if not mp3_path.exists():
            self._audio_runner._extract(video_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            processor = TranscribeProcessor()
            transcription = processor.transcribe(
                audio_file=str(mp3_path),
                output_dir=tmp_dir,
                namespace=video.stem,
                model=model,
                language=language,
                device=device,
            )

        # Pass the full transcription through — don't cherry-pick fields
        MetadataManager().update(video_path, "link2video/auto/transcribe", transcription.to_dict())

        return {"yaml_path": str(video.with_suffix(".yaml"))}
