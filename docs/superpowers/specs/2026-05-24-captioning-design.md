# Captioning Feature Design

**Date**: 2026-05-24
**Branch**: feature/captioning
**Scope**: Ollama vision-based video captioning — processor module + app batch tab. Dashboard is out of scope (separate spec).

---

## Overview

Add a captioning module that extracts frames from a video at a configurable interval, sends them in rolling batches to an Ollama vision model (with accumulated context), and writes structured captions to the per-video YAML. A new app tab lets users batch-process a folder of videos with a pre-flight metadata check before running.

---

## Part 1: Captioning Processor

### Location

`link2video/auto/caption/` — mirrors the structure of `extract_audio/` and `transcribe/`.

```
link2video/auto/caption/
    __init__.py
    processor.py
    models.py
```

### `CaptionProcessor.caption()` signature

```python
def caption(
    video_path: str,
    output_dir: str,
    namespace: str,
    interval_seconds: float = 1.0,
    sequence_length: int = 3,
    model: str = "llava",
    ollama_url: str = "http://debugx.local/ollama",
    additional_query: str = "",
    context_sections: list[str] | None = None,  # e.g. ["transcription", "comments"]
    dry_run: bool = False,
) -> "CaptionResult"
```

### Processing Steps

1. **Load YAML context** — read `{video_path}.yaml` if present; extract only the sections listed in `context_sections`. The UI uses friendly names (`"transcription"`, `"comments"`) which map to YAML keys (`"link2video/auto/transcribe"`, `"link2video/download".comments`). If the YAML does not exist or a section is missing, skip it silently.

2. **Extract frames** — call `ffmpeg` with `-vf fps=1/{interval_seconds}` to write JPEG frames into a `tempfile.mkdtemp()` directory. Frame filenames encode their timestamp: `frame_0000.jpg`, `frame_0001.jpg`, etc. Video duration is probed with `ffprobe` to compute expected frame count.

3. **Rolling batch loop** — iterate over frames in chunks of `sequence_length`:
   - Encode each frame as base64 JPEG.
   - Build Ollama prompt:
     ```
     [Optional YAML context block]
     [Optional additional_query]
     [Optional: previous captions so far]
     You are analyzing a video. Describe what you see in each image.
     Return exactly one description per image, labeled:
     Frame 1: <description>
     Frame 2: <description>
     Frame 3: <description>
     ```
   - POST to `{ollama_url}/api/generate` with `model`, `prompt`, and `images` (base64 list). Use `stream: false`.
   - Parse response: split on `Frame N:` labels → extract exactly one description per frame. If parsing fails for a frame, store `"[parse error]"` and continue.
   - Append captions to the running accumulator.

4. **Cleanup** — delete the temp frame directory.

5. **Global summary call** — single Ollama call (no images) with all accumulated captions + YAML context:
   ```
   Given the following video metadata and per-frame descriptions, write a concise overall summary.
   ```

6. **Write YAML** — call `MetadataManager().update(video_path, "link2video/auto/caption", data)`.

### YAML Output Schema

```yaml
captioning:
  global: "Overall summary of video content informed by metadata and visual analysis."
  model: llava
  interval_seconds: 1.0
  sequence_length: 3
  length: "42.3s"
  context_used:
    - transcription
    - comments
  units:
    - timestamp: 0.0
      description: "A person sits at a desk facing a camera."
    - timestamp: 1.0
      description: "The person gestures toward a whiteboard on the left."
```

### `CaptionResult` dataclass (models.py)

```python
@dataclass
class CaptionResult:
    global_summary: str
    model: str
    interval_seconds: float
    sequence_length: int
    length_seconds: float
    units: list[dict]        # [{"timestamp": float, "description": str}, ...]
    context_used: list[str]
```

### Error Handling

- Ollama unreachable → raise `RuntimeError` with the URL in the message.
- Individual frame parse failure → store `"[parse error]"` in that unit, log a warning, continue.
- `ffmpeg`/`ffprobe` not found → raise `RuntimeError`.
- `dry_run=True` → skip frame extraction and Ollama calls; return a mock `CaptionResult`.

---

## Part 2: App Batch Tab

### New Files

- `app/caption_runner.py` — `CaptionRunner` background runner
- `app/templates/caption.html` — tab template
- Routes added to `app/routes.py`

### CaptionRunner

Follows the `AudioRunner` pattern exactly:

```python
class CaptionRunner:
    def start(self, video_path, interval_seconds, sequence_length,
              model, additional_query, context_sections) -> str  # run_id
    def get(self, run_id) -> dict | None
    def clear(self, run_id) -> None
```

Internal `_run()` calls `CaptionProcessor().caption(...)` and writes status/result/error to the in-memory runs dict.

### New Routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/ollama/models` | Proxy to `{OLLAMA_URL}/api/tags`; returns `{"models": [...]}` |
| `POST` | `/api/caption` | Start a caption run; body: `{video_path, interval_seconds, sequence_length, model, additional_query, context_sections}` |
| `GET` | `/api/caption/<run_id>` | Poll run status |
| `DELETE` | `/api/caption/<run_id>` | Clear finished run |

`OLLAMA_URL` is read from app config (default: `http://debugx.local/ollama`).

### Tab UI Flow

**Step 1 — Folder scan**
- Text input for folder path + "Scan" button.
- Calls `GET /api/scan` (existing endpoint); lists `.mp4`/`.mov` files found.

**Step 2 — Global settings** (applied to all videos in the batch)
- `Analysis interval (seconds)` — number input, default `1`
- `Sequence length` — number input, default `3`
- `Ollama model` — dropdown, options from `GET /api/ollama/models`
- `Additional query` — textarea (optional)

**Step 3 — Pre-flight panel** (one row per video)

Each row shows:
- Video filename
- YAML module badges: each known module (`download`, `extract`, `transcription`, `captioning`) shown as ✓ (present) or ✗ (absent)
- Checkboxes: "Send transcription" (auto-checked if present), "Send comments" (auto-checked if present)
- Inline comment field: shown if comments section is absent; user can type a comment to be written to YAML before captioning runs

**Step 4 — Run**
- "Run All" button submits one `POST /api/caption` per video.
- Each video row shows a status badge (pending → running → complete / failed).
- Polling via `setInterval` on `GET /api/caption/<run_id>`.

### Factory Registration

`CaptionRunner` instantiated in `app/factory.py` and stored in `app.config["CAPTION_RUNNER"]`, matching the pattern for `AUDIO_RUNNER` and `TRANSCRIBE_RUNNER`.

---

## Data Flow Summary

```
User (browser)
  → POST /api/caption
  → CaptionRunner.start()
  → background thread → CaptionProcessor.caption()
      → ffmpeg (frame extraction to temp dir)
      → Ollama /api/generate (rolling batches)
      → MetadataManager.update() → video.yaml [captioning section]
  → GET /api/caption/<run_id> (polling)
  → status: completed / failed
```

---

## Testing

- `tests/auto/test_caption_processor.py` — unit tests with mocked Ollama responses and a synthetic video fixture
- `tests/test_caption_runner.py` — runner tests following the pattern of `test_audio_runner.py`
- Route tests in `tests/test_routes.py` — add caption and ollama-models endpoints

---

## Out of Scope (this spec)

- Dashboard / YAML viewer-editor (separate spec)
- Streaming progress (frame-by-frame updates to UI while running)
- Concurrent multi-video processing (currently one thread per video, sequentially scheduled)
