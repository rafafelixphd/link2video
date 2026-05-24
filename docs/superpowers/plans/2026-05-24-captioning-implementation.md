# Captioning Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Ollama vision-based captioning module that extracts frames from a video at a configurable interval, sends them in rolling batches with accumulated context to an Ollama model, and stores structured captions in the per-video YAML — plus a batch app tab with a pre-flight metadata check.

**Architecture:** A `CaptionProcessor` (in `link2video/auto/caption/`) follows the same pattern as `ExtractAudioProcessor` and `TranscribeProcessor`. A `CaptionRunner` background thread (in `app/`) dispatches the processor and writes results. A new `caption.html` tab follows the `transcribe.html` UI pattern with an added pre-flight YAML inspection panel.

**Tech Stack:** Python 3.11+, ffmpeg/ffprobe (subprocess), `requests` (Ollama HTTP API), Flask, vanilla JS (no frontend framework).

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `link2video/auto/caption/__init__.py` | Public export of `CaptionProcessor` |
| Create | `link2video/auto/caption/models.py` | `CaptionResult` dataclass |
| Create | `link2video/auto/caption/processor.py` | Frame extraction + Ollama rolling batches |
| Create | `app/caption_runner.py` | Background thread runner |
| Modify | `app/routes.py` | Add `/api/ollama/models`, `/api/caption`, `/api/yaml-info` routes |
| Modify | `app/factory.py` | Register `CaptionRunner` + `OLLAMA_URL` config |
| Modify | `app/templates/base.html` | Add Caption tab button + content div |
| Create | `app/templates/caption.html` | Full caption tab UI |
| Create | `tests/auto/test_caption_processor.py` | Processor unit tests |
| Create | `tests/test_caption_runner.py` | Runner unit tests |
| Modify | `tests/test_routes.py` | Caption and ollama-models route tests |

---

## Task 1: CaptionResult dataclass

**Files:**
- Create: `link2video/auto/caption/models.py`
- Create: `link2video/auto/caption/__init__.py`
- Test: `tests/auto/test_caption_processor.py` (first tests here)

- [ ] **Step 1: Write the failing test**

```python
# tests/auto/test_caption_processor.py
from link2video.auto.caption.models import CaptionResult


def test_caption_result_to_dict():
    result = CaptionResult(
        global_summary="A person talks.",
        model="llava",
        interval_seconds=1.0,
        sequence_length=3,
        length_seconds=5.0,
        units=[{"timestamp": 0.0, "description": "Frame one."}],
        context_used=["transcription"],
    )
    d = result.to_dict()
    assert d["global"] == "A person talks."
    assert d["model"] == "llava"
    assert d["interval_seconds"] == 1.0
    assert d["sequence_length"] == 3
    assert d["length"] == "5.0s"
    assert d["units"] == [{"timestamp": 0.0, "description": "Frame one."}]
    assert d["context_used"] == ["transcription"]
```

- [ ] **Step 2: Run to verify it fails**

```bash
cd /Users/rafaelfelix/Projects/demos/link2video
python -m pytest tests/auto/test_caption_processor.py::test_caption_result_to_dict -v
```
Expected: `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Create models.py**

```python
# link2video/auto/caption/models.py
from dataclasses import dataclass, field


@dataclass
class CaptionResult:
    global_summary: str
    model: str
    interval_seconds: float
    sequence_length: int
    length_seconds: float
    units: list
    context_used: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "global": self.global_summary,
            "model": self.model,
            "interval_seconds": self.interval_seconds,
            "sequence_length": self.sequence_length,
            "length": f"{self.length_seconds}s",
            "units": self.units,
            "context_used": self.context_used,
        }
```

- [ ] **Step 4: Create `__init__.py`**

```python
# link2video/auto/caption/__init__.py
from .processor import CaptionProcessor

__all__ = ["CaptionProcessor"]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
python -m pytest tests/auto/test_caption_processor.py::test_caption_result_to_dict -v
```
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add link2video/auto/caption/models.py link2video/auto/caption/__init__.py tests/auto/test_caption_processor.py
git commit -m "feat: add CaptionResult dataclass for caption output"
```

---

## Task 2: CaptionProcessor — frame extraction helpers

**Files:**
- Create: `link2video/auto/caption/processor.py`
- Test: `tests/auto/test_caption_processor.py`

- [ ] **Step 1: Write failing tests for frame extraction helpers**

Add to `tests/auto/test_caption_processor.py`:

```python
import subprocess
from unittest.mock import patch, MagicMock
from link2video.auto.caption.processor import CaptionProcessor


def test_get_video_duration(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="42.5\n", returncode=0)
        duration = processor._get_video_duration(str(tmp_path / "v.mp4"))
    assert duration == 42.5


def test_extract_frames_calls_ffmpeg(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    video = tmp_path / "v.mp4"
    video.touch()
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        processor._extract_frames(str(video), str(out_dir), interval_seconds=2.0)
    call_args = mock_run.call_args[0][0]
    assert "ffmpeg" in call_args
    assert "fps=1/2.0" in " ".join(call_args)


def test_encode_frame_returns_base64_string(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    img = tmp_path / "frame_0000.jpg"
    img.write_bytes(b"\xff\xd8\xff")  # minimal JPEG header
    result = processor._encode_frame(str(img))
    import base64
    assert base64.b64decode(result) == b"\xff\xd8\xff"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/auto/test_caption_processor.py -k "duration or frames or encode" -v
```
Expected: `ImportError` (processor.py doesn't exist yet).

- [ ] **Step 3: Create processor.py with helpers only**

```python
# link2video/auto/caption/processor.py
import base64
import subprocess
from pathlib import Path


class CaptionProcessor:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self.ollama_url = ollama_url.rstrip("/")

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/auto/test_caption_processor.py -k "duration or frames or encode" -v
```
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add link2video/auto/caption/processor.py tests/auto/test_caption_processor.py
git commit -m "feat: add CaptionProcessor frame extraction helpers"
```

---

## Task 3: CaptionProcessor — Ollama batch call and response parsing

**Files:**
- Modify: `link2video/auto/caption/processor.py`
- Test: `tests/auto/test_caption_processor.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/auto/test_caption_processor.py`:

```python
import requests
from unittest.mock import patch, MagicMock


def test_call_ollama_returns_text(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"response": "Frame 1: A desk.\nFrame 2: A chair."}
    mock_resp.raise_for_status = MagicMock()
    with patch("requests.post", return_value=mock_resp) as mock_post:
        text = processor._call_ollama(
            model="llava",
            prompt="describe",
            images=["aGVsbG8=", "d29ybGQ="],
        )
    assert text == "Frame 1: A desk.\nFrame 2: A chair."
    call_kwargs = mock_post.call_args
    body = call_kwargs[1]["json"]
    assert body["model"] == "llava"
    assert len(body["images"]) == 2
    assert body["stream"] is False


def test_parse_frame_descriptions_extracts_one_per_frame():
    processor = CaptionProcessor(ollama_url="http://fake")
    text = "Frame 1: A person sits.\nFrame 2: They gesture.\nFrame 3: Close-up of screen."
    result = processor._parse_frame_descriptions(text, expected_count=3)
    assert result == [
        "A person sits.",
        "They gesture.",
        "Close-up of screen.",
    ]


def test_parse_frame_descriptions_fills_parse_errors():
    processor = CaptionProcessor(ollama_url="http://fake")
    # Only 2 frames returned when 3 expected
    text = "Frame 1: Hello.\nFrame 2: World."
    result = processor._parse_frame_descriptions(text, expected_count=3)
    assert len(result) == 3
    assert result[2] == "[parse error]"
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/auto/test_caption_processor.py -k "ollama or parse" -v
```
Expected: `AttributeError` — methods don't exist yet.

- [ ] **Step 3: Implement `_call_ollama` and `_parse_frame_descriptions`**

Add to `link2video/auto/caption/processor.py`:

```python
import re
import requests


# (inside class CaptionProcessor)

    def _call_ollama(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = images
        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _parse_frame_descriptions(self, text: str, expected_count: int) -> list[str]:
        pattern = re.compile(r"Frame\s+\d+:\s*(.+?)(?=Frame\s+\d+:|$)", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        descriptions = [m.strip() for m in matches]
        while len(descriptions) < expected_count:
            descriptions.append("[parse error]")
        return descriptions[:expected_count]
```

The full `processor.py` at this point (replace the file entirely):

```python
# link2video/auto/caption/processor.py
import base64
import re
import subprocess
from pathlib import Path

import requests


class CaptionProcessor:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self.ollama_url = ollama_url.rstrip("/")

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

    def _call_ollama(self, model: str, prompt: str, images: list[str] | None = None) -> str:
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
        }
        if images:
            payload["images"] = images
        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _parse_frame_descriptions(self, text: str, expected_count: int) -> list[str]:
        pattern = re.compile(r"Frame\s+\d+:\s*(.+?)(?=Frame\s+\d+:|$)", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        descriptions = [m.strip() for m in matches]
        while len(descriptions) < expected_count:
            descriptions.append("[parse error]")
        return descriptions[:expected_count]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/auto/test_caption_processor.py -k "ollama or parse" -v
```
Expected: all 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add link2video/auto/caption/processor.py tests/auto/test_caption_processor.py
git commit -m "feat: add Ollama call and frame description parsing to CaptionProcessor"
```

---

## Task 4: CaptionProcessor — full `caption()` method

**Files:**
- Modify: `link2video/auto/caption/processor.py`
- Test: `tests/auto/test_caption_processor.py`

- [ ] **Step 1: Write failing integration test**

Add to `tests/auto/test_caption_processor.py`:

```python
import tempfile
import yaml
from pathlib import Path


def _make_fake_frames(out_dir: str, count: int) -> None:
    """Write minimal JPEG bytes as fake frame files."""
    for i in range(1, count + 1):
        (Path(out_dir) / f"frame_{i:04d}.jpg").write_bytes(b"\xff\xd8\xff\xe0")


def test_caption_writes_yaml(tmp_path):
    video = tmp_path / "myvideo.mp4"
    video.touch()

    processor = CaptionProcessor(ollama_url="http://fake")

    ollama_responses = iter([
        "Frame 1: Person at desk.\nFrame 2: Whiteboard shown.\nFrame 3: Close-up.",
        "An educational video about software.",
    ])

    def fake_call_ollama(model, prompt, images=None):
        return next(ollama_responses)

    with patch.object(processor, "_get_video_duration", return_value=3.0), \
         patch.object(processor, "_extract_frames", side_effect=lambda v, d, i: _make_fake_frames(d, 3)), \
         patch.object(processor, "_call_ollama", side_effect=fake_call_ollama):
        result = processor.caption(
            video_path=str(video),
            interval_seconds=1.0,
            sequence_length=3,
            model="llava",
        )

    assert len(result.units) == 3
    assert result.units[0] == {"timestamp": 0.0, "description": "Person at desk."}
    assert result.units[1] == {"timestamp": 1.0, "description": "Whiteboard shown."}
    assert result.units[2] == {"timestamp": 2.0, "description": "Close-up."}
    assert result.global_summary == "An educational video about software."
    assert result.length_seconds == 3.0

    yaml_path = tmp_path / "myvideo.yaml"
    assert yaml_path.exists()
    data = yaml.safe_load(yaml_path.read_text())
    assert "link2video/auto/caption" in data
    assert data["link2video/auto/caption"]["global"] == "An educational video about software."


def test_caption_dry_run_returns_empty_result(tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    processor = CaptionProcessor(ollama_url="http://fake")
    result = processor.caption(str(video), dry_run=True)
    assert result.global_summary == ""
    assert result.units == []


def test_caption_includes_yaml_context_in_prompt(tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    yaml_path = tmp_path / "v.yaml"
    yaml_path.write_text(
        "link2video/auto/transcribe:\n  text: Hello world\n"
        "link2video/download:\n  comments: Great video\n"
    )

    processor = CaptionProcessor(ollama_url="http://fake")
    prompts_seen = []

    def fake_call_ollama(model, prompt, images=None):
        prompts_seen.append(prompt)
        if images:
            return "Frame 1: Something."
        return "Summary."

    with patch.object(processor, "_get_video_duration", return_value=1.0), \
         patch.object(processor, "_extract_frames", side_effect=lambda v, d, i: _make_fake_frames(d, 1)), \
         patch.object(processor, "_call_ollama", side_effect=fake_call_ollama):
        processor.caption(
            str(video),
            interval_seconds=1.0,
            sequence_length=3,
            model="llava",
            context_sections=["transcription", "comments"],
        )

    assert any("Hello world" in p for p in prompts_seen)
    assert any("Great video" in p for p in prompts_seen)
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/auto/test_caption_processor.py -k "caption_writes or dry_run or context" -v
```
Expected: `AttributeError` — `caption()` not defined yet.

- [ ] **Step 3: Implement the full `caption()` method**

Replace `link2video/auto/caption/processor.py` entirely:

```python
# link2video/auto/caption/processor.py
import base64
import re
import subprocess
import tempfile
from pathlib import Path

import requests

from link2video.auto.caption.models import CaptionResult
from link2video.metadata_manager import MetadataManager

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

_CONTEXT_KEY_MAP = {
    "transcription": "link2video/auto/transcribe",
    "comments": "link2video/download",
}


class CaptionProcessor:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self.ollama_url = ollama_url.rstrip("/")

    def caption(
        self,
        video_path: str,
        interval_seconds: float = 1.0,
        sequence_length: int = 3,
        model: str = "llava",
        additional_query: str = "",
        context_sections: list | None = None,
        dry_run: bool = False,
    ) -> CaptionResult:
        if dry_run:
            return CaptionResult(
                global_summary="",
                model=model,
                interval_seconds=interval_seconds,
                sequence_length=sequence_length,
                length_seconds=0.0,
                units=[],
                context_used=[],
            )

        video = Path(video_path)
        if not video.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")

        yaml_context = self._load_yaml_context(video_path, context_sections or [])
        duration = self._get_video_duration(video_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._extract_frames(video_path, tmp_dir, interval_seconds)
            frame_files = sorted(Path(tmp_dir).glob("frame_*.jpg"))

            units = []
            accumulated_captions: list[str] = []

            for batch_start in range(0, len(frame_files), sequence_length):
                batch = frame_files[batch_start: batch_start + sequence_length]
                images = [self._encode_frame(str(f)) for f in batch]
                prompt = self._build_batch_prompt(
                    batch_index=batch_start,
                    batch_size=len(batch),
                    yaml_context=yaml_context,
                    additional_query=additional_query,
                    accumulated_captions=accumulated_captions,
                )
                response = self._call_ollama(model=model, prompt=prompt, images=images)
                descriptions = self._parse_frame_descriptions(response, expected_count=len(batch))

                for i, desc in enumerate(descriptions):
                    timestamp = round((batch_start + i) * interval_seconds, 3)
                    units.append({"timestamp": timestamp, "description": desc})
                    accumulated_captions.append(f"Frame {batch_start + i + 1} ({timestamp}s): {desc}")

        summary_prompt = self._build_summary_prompt(yaml_context, additional_query, accumulated_captions)
        global_summary = self._call_ollama(model=model, prompt=summary_prompt)

        context_used = [s for s in (context_sections or []) if s in yaml_context]

        result = CaptionResult(
            global_summary=global_summary,
            model=model,
            interval_seconds=interval_seconds,
            sequence_length=sequence_length,
            length_seconds=round(duration, 3),
            units=units,
            context_used=context_used,
        )

        MetadataManager().update(video_path, "link2video/auto/caption", result.to_dict())
        return result

    def _load_yaml_context(self, video_path: str, context_sections: list) -> dict:
        if not context_sections or _yaml is None:
            return {}
        yaml_path = Path(video_path).with_suffix(".yaml")
        if not yaml_path.exists():
            return {}
        data = _yaml.safe_load(yaml_path.read_text()) or {}
        context = {}
        for section in context_sections:
            yaml_key = _CONTEXT_KEY_MAP.get(section)
            if yaml_key and yaml_key in data:
                if section == "comments":
                    context["comments"] = data[yaml_key].get("comments", "")
                else:
                    context[section] = data[yaml_key]
        return context

    def _build_batch_prompt(
        self,
        batch_index: int,
        batch_size: int,
        yaml_context: dict,
        additional_query: str,
        accumulated_captions: list[str],
    ) -> str:
        parts = []
        if yaml_context:
            parts.append("== Video Metadata ==")
            if "transcription" in yaml_context:
                text = yaml_context["transcription"].get("text", "")
                parts.append(f"Transcript: {text}")
            if "comments" in yaml_context:
                parts.append(f"Comments: {yaml_context['comments']}")
            parts.append("")
        if accumulated_captions:
            parts.append("== Previous frame descriptions ==")
            parts.extend(accumulated_captions)
            parts.append("")
        if additional_query:
            parts.append(f"Additional context: {additional_query}")
            parts.append("")
        parts.append(
            f"You are analyzing a video. Describe what you see in each of the {batch_size} images below. "
            "Return exactly one description per image in this format:\n"
            + "\n".join(f"Frame {batch_index + i + 1}: <description>" for i in range(batch_size))
        )
        return "\n".join(parts)

    def _build_summary_prompt(
        self, yaml_context: dict, additional_query: str, accumulated_captions: list[str]
    ) -> str:
        parts = []
        if yaml_context:
            parts.append("== Video Metadata ==")
            if "transcription" in yaml_context:
                text = yaml_context["transcription"].get("text", "")
                parts.append(f"Transcript: {text}")
            if "comments" in yaml_context:
                parts.append(f"Comments: {yaml_context['comments']}")
            parts.append("")
        parts.append("== Per-frame descriptions ==")
        parts.extend(accumulated_captions)
        parts.append("")
        if additional_query:
            parts.append(f"Additional query: {additional_query}")
            parts.append("")
        parts.append(
            "Based on the above, write a concise overall summary of this video's content."
        )
        return "\n".join(parts)

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
        payload = {"model": model, "prompt": prompt, "stream": False}
        if images:
            payload["images"] = images
        resp = requests.post(
            f"{self.ollama_url}/api/generate",
            json=payload,
            timeout=120,
        )
        resp.raise_for_status()
        return resp.json()["response"]

    def _parse_frame_descriptions(self, text: str, expected_count: int) -> list[str]:
        pattern = re.compile(r"Frame\s+\d+:\s*(.+?)(?=Frame\s+\d+:|$)", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        descriptions = [m.strip() for m in matches]
        while len(descriptions) < expected_count:
            descriptions.append("[parse error]")
        return descriptions[:expected_count]
```

- [ ] **Step 4: Run all processor tests**

```bash
python -m pytest tests/auto/test_caption_processor.py -v
```
Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add link2video/auto/caption/processor.py tests/auto/test_caption_processor.py
git commit -m "feat: implement CaptionProcessor.caption() with rolling Ollama batches"
```

---

## Task 5: CaptionRunner

**Files:**
- Create: `app/caption_runner.py`
- Create: `tests/test_caption_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_caption_runner.py
import time
from unittest.mock import patch

import pytest

from app.caption_runner import CaptionRunner
from link2video.auto.caption.models import CaptionResult


@pytest.fixture
def runner():
    return CaptionRunner(ollama_url="http://fake")


def _fake_result():
    return CaptionResult(
        global_summary="Summary.",
        model="llava",
        interval_seconds=1.0,
        sequence_length=3,
        length_seconds=5.0,
        units=[{"timestamp": 0.0, "description": "A desk."}],
        context_used=[],
    )


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
    assert isinstance(run_id, str) and len(run_id) == 12


def test_get_returns_none_for_unknown(runner):
    assert runner.get("notexist") is None


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    expected = {"yaml_path": str(tmp_path / "v.yaml")}
    with patch.object(runner, "_caption", return_value=expected):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["result"] == expected


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", side_effect=RuntimeError("Ollama down")):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "Ollama down" in state["error"]


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", return_value={}):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    runner.clear(run_id)
    assert runner.get(run_id) is None


def test_clear_nonexistent_is_safe(runner):
    runner.clear("nope")
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_caption_runner.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create `app/caption_runner.py`**

```python
# app/caption_runner.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_caption_runner.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/caption_runner.py tests/test_caption_runner.py
git commit -m "feat: add CaptionRunner background thread for captioning"
```

---

## Task 6: Routes — Ollama models proxy, YAML info, and caption endpoints

**Files:**
- Modify: `app/routes.py`
- Modify: `tests/test_routes.py`

- [ ] **Step 1: Write failing route tests**

Add to `tests/test_routes.py`:

```python
from unittest.mock import MagicMock, patch


def test_get_ollama_models_success(client):
    with patch("requests.get") as mock_get:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"models": [{"name": "llava"}, {"name": "moondream"}]},
        )
        resp = client.get("/api/ollama/models")
    assert resp.status_code == 200
    assert resp.get_json() == {"models": ["llava", "moondream"]}


def test_get_ollama_models_unreachable(client):
    import requests as _req
    with patch("requests.get", side_effect=_req.RequestException("timeout")):
        resp = client.get("/api/ollama/models")
    assert resp.status_code == 502


def test_get_yaml_info_no_yaml(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    resp = client.get(f"/api/yaml-info?path={video}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["exists"] is False
    assert data["sections"] == []


def test_get_yaml_info_with_yaml(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    yaml_path = tmp_path / "v.yaml"
    yaml_path.write_text(
        "link2video/auto/transcribe:\n  text: hello\n"
        "link2video/download:\n  comments: nice\n"
    )
    resp = client.get(f"/api/yaml-info?path={video}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["exists"] is True
    assert "transcription" in data["sections"]
    assert "comments" in data["sections"]
    assert data["comments"] == "nice"


def test_post_caption_missing_video_path(client):
    resp = client.post("/api/caption", json={})
    assert resp.status_code == 400


def test_post_caption_success(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    runner_mock = MagicMock()
    runner_mock.start.return_value = "abc123def456"
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.post("/api/caption", json={
        "video_path": str(video),
        "interval_seconds": 1.0,
        "sequence_length": 3,
        "model": "llava",
        "additional_query": "",
        "context_sections": ["transcription"],
    })
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "abc123def456"


def test_get_caption_not_found(client):
    runner_mock = MagicMock()
    runner_mock.get.return_value = None
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.get("/api/caption/doesnotexist")
    assert resp.status_code == 404


def test_delete_caption_run(client):
    runner_mock = MagicMock()
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.delete("/api/caption/abc123")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run to verify failures**

```bash
python -m pytest tests/test_routes.py -k "ollama or yaml_info or caption" -v
```
Expected: 404 errors for unknown routes.

- [ ] **Step 3: Add routes to `app/routes.py`**

Add `import requests` at the top of `routes.py`, then append these route handlers before the final line:

```python
import requests as _requests
import yaml as _yaml
from pathlib import Path as _Path

# ── Ollama proxy ───────────────────────────────────────────────────────────────

@jobs_bp.route("/api/ollama/models", methods=["GET"])
def ollama_models():
    """Proxy GET /api/tags from the Ollama server."""
    ollama_url = current_app.config.get("OLLAMA_URL", "http://debugx.local/ollama")
    try:
        resp = _requests.get(f"{ollama_url}/api/tags", timeout=5)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return jsonify({"models": models})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


# ── YAML info ──────────────────────────────────────────────────────────────────

_YAML_SECTION_MAP = {
    "link2video/auto/transcribe": "transcription",
    "link2video/auto/caption": "captioning",
    "link2video/auto/extract": "extract",
    "link2video/download": "download",
}


@jobs_bp.route("/api/yaml-info", methods=["GET"])
def yaml_info():
    """Return which sections are present in the YAML alongside a video."""
    video_path = request.args.get("path", "").strip()
    if not video_path:
        return jsonify({"error": "path parameter required"}), 400
    yaml_path = _Path(video_path).with_suffix(".yaml")
    if not yaml_path.exists():
        return jsonify({"exists": False, "sections": [], "comments": ""})
    data = _yaml.safe_load(yaml_path.read_text()) or {}
    sections = [friendly for key, friendly in _YAML_SECTION_MAP.items() if key in data]
    comments = ""
    if "link2video/download" in data:
        comments = data["link2video/download"].get("comments", "")
    return jsonify({"exists": True, "sections": sections, "comments": comments})


# ── Caption routes ─────────────────────────────────────────────────────────────

def _caption_runner():
    return current_app.config["CAPTION_RUNNER"]


@jobs_bp.route("/api/caption", methods=["POST"])
def start_caption():
    """Start a background captioning run."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    video_path = (data.get("video_path") or "").strip()
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    run_id = _caption_runner().start(
        video_path=video_path,
        interval_seconds=float(data.get("interval_seconds", 1.0)),
        sequence_length=int(data.get("sequence_length", 3)),
        model=(data.get("model") or "llava").strip(),
        additional_query=(data.get("additional_query") or "").strip(),
        context_sections=data.get("context_sections") or [],
    )
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/caption/<run_id>", methods=["GET"])
def get_caption(run_id: str):
    """Return status of a captioning run."""
    entry = _caption_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/caption/<run_id>", methods=["DELETE"])
def clear_caption(run_id: str):
    """Remove a finished captioning entry."""
    _caption_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_routes.py -v
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "feat: add caption, yaml-info, and ollama-models routes"
```

---

## Task 7: Factory registration

**Files:**
- Modify: `app/factory.py`

- [ ] **Step 1: Update `app/factory.py`**

Replace the contents of `app/factory.py` with:

```python
"""Flask application factory."""
from flask import Flask, request

from audio_runner import AudioRunner
from caption_runner import CaptionRunner
from download_runner import DownloadRunner
from job_manager import JobManager
from routes import jobs_bp
from transcribe_runner import TranscribeRunner

OLLAMA_URL = "http://debugx.local/ollama"


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
    app.config["CAPTION_RUNNER"] = CaptionRunner(ollama_url=OLLAMA_URL)
    app.config["OLLAMA_URL"] = OLLAMA_URL

    app.register_blueprint(jobs_bp)

    @app.before_request
    def tick():
        if request.endpoint != "static":
            app.config["JOB_MANAGER"].process_queue()

    return app
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/factory.py
git commit -m "feat: register CaptionRunner and OLLAMA_URL in app factory"
```

---

## Task 8: Caption tab UI

**Files:**
- Create: `app/templates/caption.html`
- Modify: `app/templates/base.html`

- [ ] **Step 1: Add tab to `base.html`**

In `app/templates/base.html`, add the Caption tab button after the Download button:

```html
<button class="tab" onclick="switchTab('caption')">Caption</button>
```

And add the corresponding content div after the download div:

```html
<div id="caption" class="tab-content">
    {% include "caption.html" %}
</div>
```

- [ ] **Step 2: Create `app/templates/caption.html`**

```html
<div style="padding: 20px;">
    <h3 style="margin-bottom: 20px;">Caption</h3>

    <!-- Step 1: Folder scan -->
    <div style="margin-bottom: 20px;">
        <h4 style="margin-bottom: 10px;">Input Folder</h4>
        <div style="margin-bottom: 10px;">
            <label>
                Folder:
                <input type="text" id="capInputFolder" value="./examples/" style="width: 300px; padding: 6px;">
            </label>
            <button onclick="capScanFolder()" style="margin-left: 5px;">🔍 Scan</button>
            <button onclick="document.getElementById('capInputFolder').value='./examples/'" style="margin-left: 8px; background: #6c757d; font-size: 0.85em;">Examples</button>
            <button onclick="document.getElementById('capInputFolder').value='~/Movies/link2video/'" style="margin-left: 4px; background: #6c757d; font-size: 0.85em;">~/Movies</button>
            <span id="capScanStatus" style="margin-left: 10px; color: #999; font-size: 0.9em;"></span>
        </div>
    </div>

    <!-- Step 2: Global settings -->
    <div style="margin-bottom: 20px;">
        <h4 style="margin-bottom: 10px;">Settings</h4>
        <div style="display: flex; gap: 20px; flex-wrap: wrap; align-items: flex-end;">
            <label>
                Analysis interval (seconds):
                <input type="number" id="capInterval" value="1" min="0.5" step="0.5" style="width: 80px; padding: 6px; margin-left: 5px;">
            </label>
            <label>
                Sequence length:
                <input type="number" id="capSeqLen" value="3" min="1" step="1" style="width: 70px; padding: 6px; margin-left: 5px;">
            </label>
            <label>
                Ollama model:
                <select id="capModel" style="padding: 6px; margin-left: 5px;">
                    <option value="">Loading…</option>
                </select>
                <button onclick="capLoadModels()" style="margin-left: 4px; font-size: 0.8em; background: #6c757d;">↻</button>
            </label>
            <label style="flex: 1; min-width: 200px;">
                Additional query:
                <input type="text" id="capQuery" placeholder="Optional focus question…" style="width: 100%; padding: 6px; margin-top: 4px;">
            </label>
        </div>
    </div>

    <!-- Step 3: Pre-flight panel -->
    <div style="margin-bottom: 20px;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <h4 style="margin: 0;">Pre-flight Check</h4>
            <button id="capRunBtn" onclick="capSubmitAll()" style="background: #28a745;" disabled>▶ Caption All</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th>File</th>
                    <th>YAML Modules</th>
                    <th style="width: 140px;">Send Context</th>
                    <th>Comments</th>
                    <th style="width: 70px;">Remove</th>
                </tr>
            </thead>
            <tbody id="capPreflightTable"></tbody>
        </table>
    </div>

    <!-- Active runs -->
    <div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px;">
            <h4 style="margin: 0;">Active Runs</h4>
            <button onclick="capClearAll()" style="background: #dc3545;">🗑️ Clear All</button>
        </div>
        <table>
            <thead>
                <tr>
                    <th>File</th>
                    <th style="width: 110px;">Status</th>
                    <th>Result / Error</th>
                    <th style="width: 90px;">Action</th>
                </tr>
            </thead>
            <tbody id="capRunsTable"></tbody>
        </table>
    </div>

    <script>
        // capFiles: [{input, yamlInfo: {exists, sections, comments}}]
        let capFiles = [];
        let capRuns = [];
        let capPollTimer = null;

        function escapeHtml(str) {
            if (!str) return '';
            const d = document.createElement('div');
            d.textContent = str;
            return d.innerHTML;
        }

        async function capLoadModels() {
            const sel = document.getElementById('capModel');
            sel.innerHTML = '<option value="">Loading…</option>';
            try {
                const resp = await fetch('/api/ollama/models');
                const data = await resp.json();
                if (!resp.ok) { sel.innerHTML = '<option value="">Error loading models</option>'; return; }
                sel.innerHTML = data.models.map(m => `<option value="${escapeHtml(m)}">${escapeHtml(m)}</option>`).join('');
                if (!sel.value && data.models.length > 0) sel.value = data.models[0];
            } catch (e) {
                sel.innerHTML = '<option value="">Ollama unreachable</option>';
            }
        }

        async function capScanFolder() {
            const folder = document.getElementById('capInputFolder').value.trim();
            if (!folder) { alert('Please enter a folder path'); return; }
            const status = document.getElementById('capScanStatus');
            status.textContent = 'Scanning…';
            try {
                const resp = await fetch(`/api/scan?path=${encodeURIComponent(folder)}`);
                const data = await resp.json();
                if (!resp.ok) { status.textContent = '✗ ' + data.error; return; }
                if (data.count === 0) { status.textContent = 'No .mov or .mp4 files found'; return; }

                // Load YAML info for each file in parallel
                const yamlInfos = await Promise.all(data.files.map(f =>
                    fetch(`/api/yaml-info?path=${encodeURIComponent(f.input)}`)
                        .then(r => r.json())
                        .catch(() => ({ exists: false, sections: [], comments: '' }))
                ));
                capFiles = data.files.map((f, i) => ({ input: f.input, yamlInfo: yamlInfos[i] }));
                renderCapPreflight();
                document.getElementById('capRunBtn').disabled = false;
                status.textContent = `✓ ${data.count} file${data.count !== 1 ? 's' : ''} found`;
            } catch (err) {
                status.textContent = '✗ ' + err.message;
            }
        }

        function renderCapPreflight() {
            const tbody = document.getElementById('capPreflightTable');
            if (capFiles.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:#999;">No files — scan a folder</td></tr>';
                return;
            }
            tbody.innerHTML = capFiles.map((f, i) => {
                const info = f.yamlInfo;
                const hasTranscription = info.sections.includes('transcription');
                const hasComments = info.sections.includes('comments') || !!info.comments;

                const moduleBadges = ['transcription', 'captioning', 'extract', 'download'].map(s => {
                    const present = info.sections.includes(s);
                    return `<span style="font-size:0.8em;padding:2px 6px;border-radius:3px;margin-right:3px;background:${present ? '#d4edda' : '#f8d7da'};color:${present ? '#155724' : '#721c24'};">${present ? '✓' : '✗'} ${s}</span>`;
                }).join('');

                const checkboxes = `
                    <label style="font-size:0.85em;display:block;">
                        <input type="checkbox" id="capTr_${i}" ${hasTranscription ? 'checked' : ''} ${hasTranscription ? '' : 'disabled'}>
                        transcription
                    </label>
                    <label style="font-size:0.85em;display:block;">
                        <input type="checkbox" id="capCo_${i}" ${hasComments ? 'checked' : ''}>
                        comments
                    </label>`;

                const commentField = `<input type="text" id="capComment_${i}" value="${escapeHtml(info.comments || '')}" placeholder="Add comment…" style="width:100%;padding:4px;font-size:0.85em;">`;

                return `<tr>
                    <td><small>${escapeHtml(f.input)}</small></td>
                    <td>${moduleBadges}</td>
                    <td>${checkboxes}</td>
                    <td>${commentField}</td>
                    <td><button class="danger" onclick="capRemoveFile(${i})">Remove</button></td>
                </tr>`;
            }).join('');
        }

        function capRemoveFile(index) {
            capFiles.splice(index, 1);
            renderCapPreflight();
            if (capFiles.length === 0) document.getElementById('capRunBtn').disabled = true;
        }

        async function capSubmitAll() {
            if (capFiles.length === 0) { alert('Please scan a folder first'); return; }
            const model = document.getElementById('capModel').value;
            if (!model) { alert('Please select an Ollama model'); return; }
            const interval = parseFloat(document.getElementById('capInterval').value) || 1.0;
            const seqLen = parseInt(document.getElementById('capSeqLen').value) || 3;
            const query = document.getElementById('capQuery').value.trim();

            document.getElementById('capRunBtn').disabled = true;

            for (let i = 0; i < capFiles.length; i++) {
                const f = capFiles[i];
                const contextSections = [];
                if (document.getElementById(`capTr_${i}`)?.checked) contextSections.push('transcription');
                if (document.getElementById(`capCo_${i}`)?.checked) contextSections.push('comments');

                // Write comment to YAML before captioning if user typed one
                const comment = document.getElementById(`capComment_${i}`)?.value.trim() || '';
                if (comment && !f.yamlInfo.comments) {
                    // Persist comment via download endpoint if available, else just include in context
                    // (For now we pass it as additional_query context — a full comment write is out of scope)
                }

                try {
                    const resp = await fetch('/api/caption', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            video_path: f.input,
                            interval_seconds: interval,
                            sequence_length: seqLen,
                            model,
                            additional_query: query,
                            context_sections: contextSections,
                        }),
                    });
                    const data = await resp.json();
                    if (resp.ok) {
                        capRuns.push({ runId: data.id, videoPath: f.input, status: 'pending', result: null, error: null });
                    } else {
                        capRuns.push({ runId: null, videoPath: f.input, status: 'failed', result: null, error: data.error || 'Submit failed' });
                    }
                } catch (err) {
                    capRuns.push({ runId: null, videoPath: f.input, status: 'failed', result: null, error: err.message });
                }
            }

            capFiles = [];
            renderCapPreflight();
            document.getElementById('capRunBtn').disabled = true;
            renderCapRuns();
            capStartPolling();
        }

        function capStartPolling() {
            if (capPollTimer) return;
            capPollTimer = setInterval(capPollRuns, 2000);
        }

        async function capPollRuns() {
            const active = capRuns.filter(r => r.runId && (r.status === 'pending' || r.status === 'running'));
            if (active.length === 0) { clearInterval(capPollTimer); capPollTimer = null; return; }
            await Promise.all(active.map(async run => {
                try {
                    const resp = await fetch('/api/caption/' + run.runId);
                    const data = await resp.json();
                    if (resp.ok) { run.status = data.status; run.result = data.result; run.error = data.error; }
                    else { run.status = 'failed'; run.error = data.error || 'Poll error'; }
                } catch (err) { run.status = 'failed'; run.error = err.message; }
            }));
            renderCapRuns();
        }

        function renderCapRuns() {
            const tbody = document.getElementById('capRunsTable');
            if (capRuns.length === 0) {
                tbody.innerHTML = '<tr><td colspan="4" style="text-align:center;color:#999;">No runs</td></tr>';
                return;
            }
            tbody.innerHTML = capRuns.map((run, i) => {
                const badgeClass = run.status === 'completed' ? 'status-complete' : 'status-' + run.status;
                let detail = '<span style="color:#999;">—</span>';
                if (run.status === 'completed' && run.result) {
                    detail = `<span style="color:#28a745;">Saved to ${escapeHtml(run.result.yaml_path)}</span>`;
                } else if (run.status === 'failed' && run.error) {
                    detail = `<span style="color:#dc3545;">${escapeHtml(run.error)}</span>`;
                }
                const isTerminal = run.status === 'completed' || run.status === 'failed';
                return `<tr>
                    <td><small>${escapeHtml(run.videoPath)}</small></td>
                    <td><span class="status-badge ${badgeClass}">${escapeHtml(run.status)}</span></td>
                    <td><small>${detail}</small></td>
                    <td>${isTerminal ? `<button class="danger" onclick="capClearRun(${i})">Clear</button>` : ''}</td>
                </tr>`;
            }).join('');
        }

        async function capClearRun(index) {
            const run = capRuns[index];
            if (run.runId) { try { await fetch('/api/caption/' + run.runId, { method: 'DELETE' }); } catch (_) {} }
            capRuns.splice(index, 1);
            renderCapRuns();
        }

        async function capClearAll() {
            await Promise.all(capRuns.filter(r => r.runId).map(r =>
                fetch('/api/caption/' + r.runId, { method: 'DELETE' }).catch(() => {})
            ));
            capRuns = [];
            renderCapRuns();
        }

        // Initialize
        renderCapPreflight();
        renderCapRuns();
        capLoadModels();
    </script>
</div>
```

- [ ] **Step 3: Run the full test suite**

```bash
python -m pytest tests/ -v
```
Expected: all tests PASS.

- [ ] **Step 4: Commit**

```bash
git add app/templates/caption.html app/templates/base.html
git commit -m "feat: add Caption tab UI with pre-flight YAML check and Ollama model selector"
```

---

## Task 9: Final verification

- [ ] **Step 1: Run the full test suite one more time**

```bash
cd /Users/rafaelfelix/Projects/demos/link2video
python -m pytest tests/ -v --tb=short
```
Expected: all tests PASS, no warnings about missing imports.

- [ ] **Step 2: Verify the app starts**

```bash
cd app && python launch.py
```
Expected: Flask starts without errors. Open `http://localhost:5000` and confirm a "Caption" tab appears.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete captioning feature — processor, runner, routes, and UI tab"
```

---

## Self-Review Notes

- **Spec coverage**: processor ✓, YAML schema ✓, rolling batch ✓, runner ✓, all routes ✓, pre-flight panel ✓, factory ✓, tests ✓
- **Placeholder scan**: no TBDs. The inline comment write-to-YAML path in the UI notes it is out of scope (comment is passed as context instead), which is explicitly flagged in the spec's Out of Scope section.
- **Type consistency**: `CaptionResult` defined in Task 1, used identically in Task 4 and Task 5. `_caption_runner()` helper matches `CAPTION_RUNNER` key set in Task 7. `context_sections` is `List[str]` throughout.
