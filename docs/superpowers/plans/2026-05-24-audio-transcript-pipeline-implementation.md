# Audio & Transcript Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire up Extract Audio and Transcribe tabs in the web UI, backed by a unified per-video YAML that accumulates metadata from all pipeline stages.

**Architecture:** A new `MetadataManager` in the library handles all YAML I/O (read-merge-write). App-layer runners (`AudioRunner`, `TranscribeRunner`) orchestrate existing processors and call `MetadataManager` — processors themselves are not modified. `TranscribeRunner` auto-extracts audio if no `.mp3` exists alongside the video.

**Tech Stack:** Python stdlib (`threading`, `uuid`, `tempfile`, `subprocess`, `json`), PyYAML, ffprobe (system), existing `ExtractAudioProcessor` and `TranscribeProcessor`, Flask

---

## File Map

| File | Action | Purpose |
|------|--------|---------|
| `link2video/metadata_manager.py` | Create | Unified YAML read-merge-write |
| `link2video/metadata.py` | Modify | Delegate `save_metadata()` to MetadataManager |
| `app/audio_runner.py` | Create | Background thread: extract audio, write YAML section |
| `app/transcribe_runner.py` | Create | Background thread: transcribe (auto-extract if needed), write YAML section |
| `app/factory.py` | Modify | Register AudioRunner and TranscribeRunner |
| `app/routes.py` | Modify | Add `/api/audio` and `/api/transcribe` routes |
| `app/templates/extract-audio.html` | Modify | Replace placeholder with form + polling |
| `app/templates/transcribe.html` | Modify | Replace placeholder with form + polling |
| `tests/test_metadata_manager.py` | Create | Unit tests for MetadataManager |
| `tests/test_metadata.py` | Modify | Update assertions for new YAML format |
| `tests/test_audio_runner.py` | Create | Unit tests for AudioRunner |
| `tests/test_transcribe_runner.py` | Create | Unit tests for TranscribeRunner |
| `tests/test_routes.py` | Modify | Add route tests for audio and transcribe endpoints |

---

## Task 1: MetadataManager

**Files:**
- Create: `link2video/metadata_manager.py`
- Create: `tests/test_metadata_manager.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_metadata_manager.py
from datetime import date
from pathlib import Path

import pytest
import yaml

from link2video.metadata_manager import MetadataManager


@pytest.fixture
def tmp_video(tmp_path):
    video = tmp_path / "my_video.mp4"
    video.touch()
    return str(video)


def test_creates_yaml_alongside_video(tmp_video):
    mgr = MetadataManager()
    yaml_path = mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    assert Path(yaml_path) == Path(tmp_video).with_suffix(".yaml")
    assert Path(yaml_path).exists()


def test_returns_yaml_path_as_string(tmp_video):
    mgr = MetadataManager()
    result = mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    assert isinstance(result, str)


def test_populates_generic_fields_on_first_write(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["name"] == "my_video"
    assert data["original_file"] == tmp_video
    assert data["date"] == str(date.today())


def test_writes_section_key_block(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com", "tags": ["a", "b"]})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["link2video/download"] == {"url": "http://x.com", "tags": ["a", "b"]}


def test_accumulates_multiple_sections(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    mgr.update(tmp_video, "link2video/auto/extract", {"format": "mp3", "duration": 10.0})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert "link2video/download" in data
    assert "link2video/auto/extract" in data


def test_overwrites_existing_section(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://old.com"})
    mgr.update(tmp_video, "link2video/download", {"url": "http://new.com"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["link2video/download"]["url"] == "http://new.com"


def test_generic_fields_not_overwritten_on_second_write(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    mgr.update(tmp_video, "link2video/auto/extract", {"format": "mp3"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["name"] == "my_video"
    assert data["original_file"] == tmp_video
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_metadata_manager.py -v
```

Expected: `ModuleNotFoundError: No module named 'link2video.metadata_manager'`

- [ ] **Step 3: Implement MetadataManager**

```python
# link2video/metadata_manager.py
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import yaml


class MetadataManager:
    def update(self, video_path: str, section_key: str, data: dict) -> str:
        """Read existing YAML alongside video_path, merge section_key, write back atomically."""
        yaml_path = Path(video_path).with_suffix(".yaml")

        existing = {}
        if yaml_path.exists():
            with open(yaml_path, "r") as f:
                existing = yaml.safe_load(f) or {}

        if "name" not in existing:
            existing["name"] = Path(video_path).stem
        if "original_file" not in existing:
            existing["original_file"] = str(video_path)
        if "date" not in existing:
            existing["date"] = str(date.today())

        existing[section_key] = data

        fd, tmp = tempfile.mkstemp(dir=yaml_path.parent, suffix=".yaml.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.safe_dump(
                    existing, f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            shutil.move(tmp, str(yaml_path))
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

        return str(yaml_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_metadata_manager.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add link2video/metadata_manager.py tests/test_metadata_manager.py
git commit -m "feat: add MetadataManager for unified per-video YAML"
```

---

## Task 2: Migrate Download Metadata

**Files:**
- Modify: `link2video/metadata.py`
- Modify: `tests/test_metadata.py`

- [ ] **Step 1: Read the current tests to understand what will break**

```bash
cat tests/test_metadata.py
```

The existing tests check for top-level keys (`url`, `date`, `tags`, `comments`). After migration these move under `link2video/download`.

- [ ] **Step 2: Update `save_metadata()` to delegate to MetadataManager**

In `link2video/metadata.py`, replace the body of `save_metadata()` while keeping its signature and docstring intact:

```python
def save_metadata(
    filename: str,
    url: str,
    tags=None,
    comments: str = ""
) -> str:
    """
    Save metadata for a video as a YAML file.

    The metadata is saved alongside the video file in the same directory.
    The metadata filename is derived from the video filename without its extension.

    Args:
        filename (str): The path to the video file
        url (str): The URL of the video source
        tags (Optional[List[str]]): List of tags (default: None)
        comments (str): Additional comments (default: "")

    Returns:
        str: The path to the saved metadata file

    Raises:
        ValueError: If url or filename is empty
    """
    if not filename:
        raise ValueError("Filename cannot be empty")
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    from link2video.metadata_manager import MetadataManager
    mgr = MetadataManager()
    return mgr.update(filename, "link2video/download", {
        "url": url,
        "tags": tags or [],
        "comments": comments,
    })
```

Leave `create_metadata()` unchanged — it is still tested and used independently.

- [ ] **Step 3: Update the metadata tests to match the new YAML structure**

Open `tests/test_metadata.py` and replace every assertion that reads top-level YAML keys with the nested `link2video/download` path. The exact lines will differ, but the pattern is:

```python
# OLD
assert data['url'] == url
assert data['tags'] == tags
assert data['comments'] == comments

# NEW
assert data['link2video/download']['url'] == url
assert data['link2video/download']['tags'] == tags
assert data['link2video/download']['comments'] == comments
```

Keep `date` check as: `assert data['date'] == str(date.today())` (it's now a generic top-level field).

Also verify these generic fields exist:
```python
assert data['name'] == Path(filename).stem
assert data['original_file'] == filename
```

- [ ] **Step 4: Run the full metadata test suite**

```bash
pytest tests/test_metadata.py -v
```

Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add link2video/metadata.py tests/test_metadata.py
git commit -m "refactor: delegate save_metadata to MetadataManager, update YAML schema"
```

---

## Task 3: AudioRunner

**Files:**
- Create: `app/audio_runner.py`
- Create: `tests/test_audio_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_audio_runner.py
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.audio_runner import AudioRunner


@pytest.fixture
def runner():
    return AudioRunner()


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={"mp3_path": str(tmp_path / "v.mp3")}):
        run_id = runner.start(str(video))
    assert isinstance(run_id, str)
    assert len(run_id) == 12


def test_get_returns_none_for_unknown_id(runner):
    assert runner.get("notarunid") is None


def test_initial_state_is_pending_or_running(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={}):
        run_id = runner.start(str(video))
    state = runner.get(run_id)
    assert state["status"] in ("pending", "running", "completed")


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={"mp3_path": str(tmp_path / "v.mp3")}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["result"] == {"mp3_path": str(tmp_path / "v.mp3")}
    assert state["error"] is None


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", side_effect=RuntimeError("ffmpeg missing")):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "ffmpeg missing" in state["error"]
    assert state["result"] is None


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    runner.clear(run_id)
    assert runner.get(run_id) is None


def test_clear_nonexistent_run_is_safe(runner):
    runner.clear("does-not-exist")  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_audio_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.audio_runner'`

- [ ] **Step 3: Implement AudioRunner**

```python
# app/audio_runner.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_audio_runner.py -v
```

Expected: all 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/audio_runner.py tests/test_audio_runner.py
git commit -m "feat: add AudioRunner background thread for audio extraction"
```

---

## Task 4: TranscribeRunner

**Files:**
- Create: `app/transcribe_runner.py`
- Create: `tests/test_transcribe_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_transcribe_runner.py
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.audio_runner import AudioRunner
from app.transcribe_runner import TranscribeRunner
from link2video.auto.transcribe.models import Transcription


def _make_transcription():
    return Transcription(
        whisper_output={
            "text": "Hello world",
            "segments": [
                {
                    "id": 0, "seek": 0, "start": 0.0, "end": 1.0,
                    "text": "Hello",
                    "tokens": [1, 2],
                    "avg_logprob": -0.1,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.01,
                    "temperature": 0.0,
                },
                {
                    "id": 1, "seek": 0, "start": 1.0, "end": 2.0,
                    "text": " world",
                    "tokens": [3, 4],
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.01,
                    "temperature": 0.0,
                },
            ],
            "language": "en",
        },
        model="base",
        device="cpu",
        timestamp="2026-05-24T00:00:00Z",
        input_file="audio.mp3",
        language_requested="en",
    )


@pytest.fixture
def audio_runner():
    return AudioRunner()


@pytest.fixture
def runner(audio_runner):
    return TranscribeRunner(audio_runner)


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video))
    assert isinstance(run_id, str)
    assert len(run_id) == 12


def test_get_returns_none_for_unknown_id(runner):
    assert runner.get("notarunid") is None


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["error"] is None


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", side_effect=RuntimeError("whisper missing")):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "whisper missing" in state["error"]


def test_auto_extracts_audio_if_mp3_missing(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    # no v.mp3 exists

    transcription = _make_transcription()
    with patch.object(audio_runner, "_extract", return_value={}) as mock_extract, \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager"):
        MockProc.return_value.transcribe.return_value = transcription
        run_id = runner.start(str(video))
        time.sleep(0.3)

    mock_extract.assert_called_once_with(str(video))


def test_skips_extraction_if_mp3_exists(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    mp3 = tmp_path / "v.mp3"
    mp3.touch()

    transcription = _make_transcription()
    with patch.object(audio_runner, "_extract") as mock_extract, \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager"):
        MockProc.return_value.transcribe.return_value = transcription
        run_id = runner.start(str(video))
        time.sleep(0.3)

    mock_extract.assert_not_called()


def test_strips_whisper_noise_from_segments(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    mp3 = tmp_path / "v.mp3"
    mp3.touch()

    transcription = _make_transcription()
    captured = {}

    def fake_update(video_path, section_key, data):
        captured.update(data)
        return "x.yaml"

    with patch.object(audio_runner, "_extract"), \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager") as MockMgr:
        MockProc.return_value.transcribe.return_value = transcription
        MockMgr.return_value.update.side_effect = fake_update
        run_id = runner.start(str(video))
        time.sleep(0.3)

    assert captured["text"] == "Hello world"
    for seg in captured["segments"]:
        assert set(seg.keys()) == {"start", "end", "text"}


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    runner.clear(run_id)
    assert runner.get(run_id) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_transcribe_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'app.transcribe_runner'`

- [ ] **Step 3: Implement TranscribeRunner**

```python
# app/transcribe_runner.py
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

        whisper = transcription.whisper_output
        segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in whisper.get("segments", [])
        ]

        MetadataManager().update(video_path, "link2video/auto/transcribe", {
            "model": transcription.model,
            "language": transcription.language_requested,
            "device": transcription.device,
            "timestamp": transcription.timestamp,
            "text": whisper.get("text", ""),
            "segments": segments,
        })

        return {"yaml_path": str(video.with_suffix(".yaml"))}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_transcribe_runner.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add app/transcribe_runner.py tests/test_transcribe_runner.py
git commit -m "feat: add TranscribeRunner with auto-extract and segment stripping"
```

---

## Task 5: Wire Factory and Routes

**Files:**
- Modify: `app/factory.py`
- Modify: `app/routes.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write the failing route tests**

Add to the bottom of `tests/test_routes.py`:

```python
from unittest.mock import MagicMock


@pytest.fixture
def client_with_runners(tmp_path):
    app = create_app(jobs_dir=str(tmp_path))
    app.config["TESTING"] = True

    mock_audio = MagicMock()
    mock_audio.start.return_value = "abc123456789"
    mock_audio.get.return_value = {"status": "completed", "result": {"mp3_path": "/v/v.mp3"}, "error": None}
    app.config["AUDIO_RUNNER"] = mock_audio

    mock_transcribe = MagicMock()
    mock_transcribe.start.return_value = "def987654321"
    mock_transcribe.get.return_value = {"status": "completed", "result": {"yaml_path": "/v/v.yaml"}, "error": None}
    app.config["TRANSCRIBE_RUNNER"] = mock_transcribe

    with app.test_client() as c:
        yield c


# Audio routes
def test_post_audio_missing_video_path(client_with_runners):
    resp = client_with_runners.post("/api/audio", json={})
    assert resp.status_code == 400
    assert "video_path" in resp.get_json()["error"]


def test_post_audio_no_body(client_with_runners):
    resp = client_with_runners.post("/api/audio")
    assert resp.status_code == 400


def test_post_audio_success(client_with_runners):
    resp = client_with_runners.post("/api/audio", json={"video_path": "/videos/v.mp4"})
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "abc123456789"


def test_get_audio_found(client_with_runners):
    resp = client_with_runners.get("/api/audio/abc123456789")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"


def test_get_audio_not_found(client_with_runners):
    client_with_runners.app.config["AUDIO_RUNNER"].get.return_value = None
    resp = client_with_runners.get("/api/audio/notexist")
    assert resp.status_code == 404


def test_delete_audio(client_with_runners):
    resp = client_with_runners.delete("/api/audio/abc123456789")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cleared"


# Transcribe routes
def test_post_transcribe_missing_video_path(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={})
    assert resp.status_code == 400


def test_post_transcribe_success(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={
        "video_path": "/videos/v.mp4",
        "model": "small",
        "language": "pt",
        "device": "cpu",
    })
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "def987654321"


def test_post_transcribe_defaults(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={"video_path": "/videos/v.mp4"})
    assert resp.status_code == 201
    # verify defaults were forwarded
    client_with_runners.app.config["TRANSCRIBE_RUNNER"].start.assert_called_with(
        "/videos/v.mp4", model="base", language="en", device="auto"
    )


def test_get_transcribe_found(client_with_runners):
    resp = client_with_runners.get("/api/transcribe/def987654321")
    assert resp.status_code == 200


def test_get_transcribe_not_found(client_with_runners):
    client_with_runners.app.config["TRANSCRIBE_RUNNER"].get.return_value = None
    resp = client_with_runners.get("/api/transcribe/notexist")
    assert resp.status_code == 404


def test_delete_transcribe(client_with_runners):
    resp = client_with_runners.delete("/api/transcribe/def987654321")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_routes.py -k "audio or transcribe" -v
```

Expected: 404 errors (routes not registered yet)

- [ ] **Step 3: Update factory to register new runners**

Replace `app/factory.py` with:

```python
"""Flask application factory."""
from flask import Flask, request

from audio_runner import AudioRunner
from download_runner import DownloadRunner
from job_manager import JobManager
from routes import jobs_bp
from transcribe_runner import TranscribeRunner


def create_app(jobs_dir: str = "app/.jobs") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")

    job_manager = JobManager(jobs_dir=jobs_dir)
    job_manager.recover()
    app.config["JOB_MANAGER"] = job_manager

    app.config["DOWNLOAD_RUNNER"] = DownloadRunner()

    audio_runner = AudioRunner()
    app.config["AUDIO_RUNNER"] = audio_runner
    app.config["TRANSCRIBE_RUNNER"] = TranscribeRunner(audio_runner)

    app.register_blueprint(jobs_bp)

    @app.before_request
    def tick():
        if request.endpoint != "static":
            app.config["JOB_MANAGER"].process_queue()

    return app
```

- [ ] **Step 4: Add audio and transcribe routes to `app/routes.py`**

Add after the last download route (line 147):

```python
# ── Audio routes ───────────────────────────────────────────────────────────────

def _audio_runner():
    return current_app.config["AUDIO_RUNNER"]


@jobs_bp.route("/api/audio", methods=["POST"])
def start_audio():
    """Start a background audio extraction."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    video_path = (data.get("video_path") or "").strip()
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    run_id = _audio_runner().start(video_path)
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/audio/<run_id>", methods=["GET"])
def get_audio(run_id: str):
    """Return status of an audio extraction run."""
    entry = _audio_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/audio/<run_id>", methods=["DELETE"])
def clear_audio(run_id: str):
    """Remove a finished audio extraction entry."""
    _audio_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200


# ── Transcribe routes ──────────────────────────────────────────────────────────

def _transcribe_runner():
    return current_app.config["TRANSCRIBE_RUNNER"]


@jobs_bp.route("/api/transcribe", methods=["POST"])
def start_transcribe():
    """Start a background transcription."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    video_path = (data.get("video_path") or "").strip()
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    model = (data.get("model") or "base").strip()
    language = (data.get("language") or "en").strip()
    device = (data.get("device") or "auto").strip()
    run_id = _transcribe_runner().start(video_path, model=model, language=language, device=device)
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/transcribe/<run_id>", methods=["GET"])
def get_transcribe(run_id: str):
    """Return status of a transcription run."""
    entry = _transcribe_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/transcribe/<run_id>", methods=["DELETE"])
def clear_transcribe(run_id: str):
    """Remove a finished transcription entry."""
    _transcribe_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200
```

- [ ] **Step 5: Run all route tests**

```bash
pytest tests/test_routes.py -v
```

Expected: all tests PASS (including the new audio/transcribe ones)

- [ ] **Step 6: Run the full test suite to check for regressions**

```bash
pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```bash
git add app/factory.py app/routes.py tests/test_routes.py
git commit -m "feat: register AudioRunner/TranscribeRunner, add audio and transcribe routes"
```

---

## Task 6: Web UI Templates

**Files:**
- Modify: `app/templates/extract-audio.html`
- Modify: `app/templates/transcribe.html`

No automated tests — verify manually by starting the dev server.

- [ ] **Step 1: Replace `app/templates/extract-audio.html`**

```html
<div style="padding: 20px;">
    <h3 style="margin-bottom: 20px;">Extract Audio</h3>

    <div style="margin-bottom: 30px;">
        <h4 style="margin-bottom: 10px;">Settings</h4>

        <div style="margin-bottom: 10px;">
            <label>
                Video File:
                <input type="text" id="audioVideoPath" placeholder="/path/to/video.mp4"
                       style="width: 500px; padding: 6px; margin-left: 5px;">
            </label>
        </div>

        <button id="audioBtn" onclick="startAudio()" style="background: #28a745;">&#127925; Extract Audio</button>
    </div>

    <div id="audioStatusSection" style="display: none;">
        <h4 style="margin-bottom: 10px;">Status</h4>
        <table>
            <thead>
                <tr>
                    <th style="width: 120px;">Status</th>
                    <th>Result / Error</th>
                    <th style="width: 100px;">Action</th>
                </tr>
            </thead>
            <tbody id="audioStatusBody"></tbody>
        </table>
    </div>

    <script>
        let audioRunId = null;
        let audioPollInterval = null;
        let audioPollErrors = 0;

        function escapeHtml(str) {
            if (!str) return '';
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }

        async function startAudio() {
            const videoPath = document.getElementById('audioVideoPath').value.trim();
            if (!videoPath) { alert('Video file path is required'); return; }

            document.getElementById('audioBtn').disabled = true;

            try {
                const resp = await fetch('/api/audio', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ video_path: videoPath }),
                });
                const data = await resp.json();
                if (!resp.ok) { alert('Error: ' + data.error); document.getElementById('audioBtn').disabled = false; return; }
                audioRunId = data.id;
                renderAudioStatus('pending', null, null);
                startAudioPolling();
            } catch (err) {
                document.getElementById('audioBtn').disabled = false;
                alert('Error: ' + err.message);
            }
        }

        function startAudioPolling() {
            audioPollErrors = 0;
            if (audioPollInterval) clearInterval(audioPollInterval);
            audioPollInterval = setInterval(async () => {
                if (!audioRunId) return;
                try {
                    const resp = await fetch('/api/audio/' + audioRunId);
                    const data = await resp.json();
                    if (!resp.ok) {
                        renderAudioStatus('failed', null, 'Server error: ' + (data.error || resp.status));
                        clearInterval(audioPollInterval); audioPollInterval = null;
                        document.getElementById('audioBtn').disabled = false;
                        return;
                    }
                    renderAudioStatus(data.status, data.result, data.error);
                    if (data.status === 'completed' || data.status === 'failed') {
                        clearInterval(audioPollInterval); audioPollInterval = null;
                        document.getElementById('audioBtn').disabled = false;
                    }
                } catch (err) {
                    audioPollErrors++;
                    if (audioPollErrors >= 5) {
                        clearInterval(audioPollInterval); audioPollInterval = null;
                        document.getElementById('audioBtn').disabled = false;
                        renderAudioStatus('failed', null, 'Connection lost. Reload and try again.');
                    }
                }
            }, 2000);
        }

        function renderAudioStatus(status, result, error) {
            document.getElementById('audioStatusSection').style.display = 'block';
            const badgeClass = status === 'completed' ? 'status-complete' : 'status-' + status;
            let detail = '<span style="color: #999;">—</span>';
            if (status === 'completed' && result) {
                detail = '<span style="color: #28a745;">' + escapeHtml(result.mp3_path) + '</span>';
            } else if (status === 'failed' && error) {
                detail = '<span style="color: #dc3545;">' + escapeHtml(error) + '</span>';
            }
            const isTerminal = status === 'completed' || status === 'failed';
            document.getElementById('audioStatusBody').innerHTML = `
                <tr>
                    <td><span class="status-badge ${badgeClass}">${escapeHtml(status)}</span></td>
                    <td><small>${detail}</small></td>
                    <td>${isTerminal ? '<button class="danger" onclick="clearAudioStatus()">Clear</button>' : ''}</td>
                </tr>
            `;
        }

        async function clearAudioStatus() {
            if (audioRunId) { await fetch('/api/audio/' + audioRunId, { method: 'DELETE' }); audioRunId = null; }
            if (audioPollInterval) { clearInterval(audioPollInterval); audioPollInterval = null; }
            document.getElementById('audioBtn').disabled = false;
            document.getElementById('audioStatusSection').style.display = 'none';
            document.getElementById('audioStatusBody').innerHTML = '';
        }
    </script>
</div>
```

- [ ] **Step 2: Replace `app/templates/transcribe.html`**

```html
<div style="padding: 20px;">
    <h3 style="margin-bottom: 20px;">Transcribe</h3>

    <div style="margin-bottom: 30px;">
        <h4 style="margin-bottom: 10px;">Settings</h4>

        <div style="margin-bottom: 10px;">
            <label>
                Video File:
                <input type="text" id="trVideoPath" placeholder="/path/to/video.mp4"
                       style="width: 500px; padding: 6px; margin-left: 5px;">
            </label>
        </div>

        <div style="margin-bottom: 10px;">
            <label>
                Model:
                <select id="trModel" style="padding: 6px; margin-left: 5px;">
                    <option value="base" selected>base</option>
                    <option value="tiny">tiny</option>
                    <option value="small">small</option>
                    <option value="medium">medium</option>
                    <option value="large">large</option>
                </select>
            </label>
        </div>

        <div style="margin-bottom: 10px;">
            <label>
                Language:
                <select id="trLanguage" style="padding: 6px; margin-left: 5px;">
                    <option value="en" selected>English</option>
                    <option value="pt">Portuguese</option>
                    <option value="ja">Japanese</option>
                </select>
            </label>
        </div>

        <div style="margin-bottom: 10px;">
            <label>
                Device:
                <select id="trDevice" style="padding: 6px; margin-left: 5px;">
                    <option value="auto" selected>auto</option>
                    <option value="cpu">cpu</option>
                    <option value="mps">mps</option>
                    <option value="cuda">cuda</option>
                </select>
            </label>
        </div>

        <p style="color: #666; font-size: 0.9em;">
            Note: if no .mp3 exists alongside the video, audio will be extracted automatically first.
        </p>

        <button id="trBtn" onclick="startTranscribe()" style="background: #28a745;">&#128221; Transcribe</button>
    </div>

    <div id="trStatusSection" style="display: none;">
        <h4 style="margin-bottom: 10px;">Status</h4>
        <table>
            <thead>
                <tr>
                    <th style="width: 120px;">Status</th>
                    <th>Result / Error</th>
                    <th style="width: 100px;">Action</th>
                </tr>
            </thead>
            <tbody id="trStatusBody"></tbody>
        </table>
    </div>

    <script>
        let trRunId = null;
        let trPollInterval = null;
        let trPollErrors = 0;

        function escapeHtml(str) {
            if (!str) return '';
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }

        async function startTranscribe() {
            const videoPath = document.getElementById('trVideoPath').value.trim();
            if (!videoPath) { alert('Video file path is required'); return; }

            const model = document.getElementById('trModel').value;
            const language = document.getElementById('trLanguage').value;
            const device = document.getElementById('trDevice').value;

            document.getElementById('trBtn').disabled = true;

            try {
                const resp = await fetch('/api/transcribe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ video_path: videoPath, model, language, device }),
                });
                const data = await resp.json();
                if (!resp.ok) { alert('Error: ' + data.error); document.getElementById('trBtn').disabled = false; return; }
                trRunId = data.id;
                renderTrStatus('pending', null, null);
                startTrPolling();
            } catch (err) {
                document.getElementById('trBtn').disabled = false;
                alert('Error: ' + err.message);
            }
        }

        function startTrPolling() {
            trPollErrors = 0;
            if (trPollInterval) clearInterval(trPollInterval);
            trPollInterval = setInterval(async () => {
                if (!trRunId) return;
                try {
                    const resp = await fetch('/api/transcribe/' + trRunId);
                    const data = await resp.json();
                    if (!resp.ok) {
                        renderTrStatus('failed', null, 'Server error: ' + (data.error || resp.status));
                        clearInterval(trPollInterval); trPollInterval = null;
                        document.getElementById('trBtn').disabled = false;
                        return;
                    }
                    renderTrStatus(data.status, data.result, data.error);
                    if (data.status === 'completed' || data.status === 'failed') {
                        clearInterval(trPollInterval); trPollInterval = null;
                        document.getElementById('trBtn').disabled = false;
                    }
                } catch (err) {
                    trPollErrors++;
                    if (trPollErrors >= 5) {
                        clearInterval(trPollInterval); trPollInterval = null;
                        document.getElementById('trBtn').disabled = false;
                        renderTrStatus('failed', null, 'Connection lost. Reload and try again.');
                    }
                }
            }, 2000);
        }

        function renderTrStatus(status, result, error) {
            document.getElementById('trStatusSection').style.display = 'block';
            const badgeClass = status === 'completed' ? 'status-complete' : 'status-' + status;
            let detail = '<span style="color: #999;">—</span>';
            if (status === 'completed' && result) {
                detail = '<span style="color: #28a745;">Transcript saved to ' + escapeHtml(result.yaml_path) + '</span>';
            } else if (status === 'failed' && error) {
                detail = '<span style="color: #dc3545;">' + escapeHtml(error) + '</span>';
            }
            const isTerminal = status === 'completed' || status === 'failed';
            document.getElementById('trStatusBody').innerHTML = `
                <tr>
                    <td><span class="status-badge ${badgeClass}">${escapeHtml(status)}</span></td>
                    <td><small>${detail}</small></td>
                    <td>${isTerminal ? '<button class="danger" onclick="clearTrStatus()">Clear</button>' : ''}</td>
                </tr>
            `;
        }

        async function clearTrStatus() {
            if (trRunId) { await fetch('/api/transcribe/' + trRunId, { method: 'DELETE' }); trRunId = null; }
            if (trPollInterval) { clearInterval(trPollInterval); trPollInterval = null; }
            document.getElementById('trBtn').disabled = false;
            document.getElementById('trStatusSection').style.display = 'none';
            document.getElementById('trStatusBody').innerHTML = '';
        }
    </script>
</div>
```

- [ ] **Step 3: Start the dev server and verify both tabs render**

```bash
cd app && python launch.py
```

Open the app in a browser, click "Extract Audio" tab — verify form appears with video path input and button. Click "Transcribe" tab — verify form appears with all dropdowns. No console errors.

- [ ] **Step 4: Commit**

```bash
git add app/templates/extract-audio.html app/templates/transcribe.html
git commit -m "feat: implement Extract Audio and Transcribe tabs in web UI"
```

---

## Task 7: Final Verification

- [ ] **Step 1: Run the complete test suite**

```bash
pytest -v
```

Expected: all tests PASS, zero failures

- [ ] **Step 2: Commit if any stray changes remain**

```bash
git status
```

If clean, no commit needed.
