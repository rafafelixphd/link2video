# Audio & Transcript Pipeline Design

**Date:** 2026-05-24
**Branch:** feature/audio-transcript
**Scope:** Complete the Extract Audio and Transcribe tabs, unify all pipeline metadata into a single YAML per video

---

## Overview

Two goals:

1. **Complete the pipeline** — wire up the existing `ExtractAudioProcessor` and `TranscribeProcessor` into the web UI (Extract Audio and Transcribe tabs)
2. **Unify metadata** — consolidate the fragmented YAML files produced by download, segmentation, audio extraction, and transcription into a single `{stem}.yaml` per video

---

## Unified Metadata Format

A single YAML file lives alongside the video, named with the same stem:

```
my_video.mp4
my_video.mp3
my_video.yaml   ← consolidated metadata
```

### Structure

```yaml
# Generic — populated on first write by any stage
name: my_video
original_file: /path/to/my_video.mp4
date: 2026-05-24

# Per-stage blocks, keyed by module path
link2video/download:
  url: https://youtube.com/watch?v=...
  tags: [tutorial, python]
  comments: ""

link2video/auto/extract:
  format: mp3
  duration: 120.5
  sample_rate: 44100
  channels: 1

link2video/auto/split:
  threshold: -10dB
  segments_count: 15
  output_dir: my_video-segments/

link2video/auto/transcribe:
  model: base
  language: en
  device: mps
  timestamp: 2026-05-24T10:30:00Z
  text: "Full transcript text here..."
  segments:
    - start: 0.0
      end: 2.5
      text: "First segment text"
    - start: 2.5
      end: 5.0
      text: "Second segment text"
```

**Key decisions:**
- Module path as section key (`link2video/auto/extract`) makes the source self-documenting and prevents collisions as new modules are added
- Generic fields (`name`, `original_file`, `date`) are written on first write by any stage
- Single YAML only — no separate JSON for transcripts; Whisper token IDs and log probabilities are stripped, only `text` and `segments[{start, end, text}]` are kept
- File placement: always alongside the video (Option A), same directory, same stem

---

## Component 1 — MetadataManager

**File:** `link2video/metadata_manager.py`

Single class, single public method:

```python
class MetadataManager:
    def update(self, video_path: str, section_key: str, data: dict) -> str:
        """
        Read existing YAML alongside video_path, merge section_key block,
        write back. Populates generic fields on first write.
        Returns the YAML path.
        """
```

Behavior:
- Derives YAML path as `Path(video_path).with_suffix('.yaml')`
- On first write: sets `name` (stem), `original_file` (video_path), `date` (today)
- Reads existing YAML if present, deep-merges `section_key` block with `data`
- Writes back atomically (write to temp file, rename)

**Migration:** `link2video/metadata.py` `save_metadata()` is updated to delegate to `MetadataManager.update(video_path, "link2video/download", {url, tags, comments})`. The existing function signature is preserved for backward compatibility.

---

## Component 2 — Processors (unchanged)

`ExtractAudioProcessor` and `TranscribeProcessor` are **not modified**. They remain pure processing units callable by any layer (CLI, tests, app).

---

## Component 3 — App Runners

Two new runners in `app/`, following the `DownloadRunner` pattern exactly (background `threading.Thread`, in-memory state dict, `uuid` run IDs).

### AudioRunner (`app/audio_runner.py`)

```python
class AudioRunner:
    def start(self, video_path: str) -> str: ...
    def get(self, run_id: str) -> Optional[dict]: ...
    def clear(self, run_id: str) -> None: ...
```

Internal `_run()`:
1. Calls `ExtractAudioProcessor.extract(input_file=video_path, output_dir=video_dir, namespace=stem, format="mp3")`
2. Reads duration/sample_rate/channels from the result
3. Calls `MetadataManager.update(video_path, "link2video/auto/extract", {...})`

### TranscribeRunner (`app/transcribe_runner.py`)

```python
class TranscribeRunner:
    def start(self, video_path: str, model: str = "base",
              language: str = "en", device: str = "auto") -> str: ...
    def get(self, run_id: str) -> Optional[dict]: ...
    def clear(self, run_id: str) -> None: ...
```

Internal `_run()`:
1. Check if `{stem}.mp3` exists alongside video — if not, call `AudioRunner._run()` inline first
2. Call `TranscribeProcessor.transcribe(audio_file=mp3_path, output_dir=video_dir, namespace=stem, model=model, language=language, device=device)`
3. Strip Whisper token IDs/log probs from result, keep `text` + `segments[{start, end, text}]`
4. Call `MetadataManager.update(video_path, "link2video/auto/transcribe", {...})`

---

## Component 4 — Routes

New routes added to `app/routes.py`:

```
POST   /api/audio               { "video_path": "..." }
GET    /api/audio/<run_id>
DELETE /api/audio/<run_id>

POST   /api/transcribe          { "video_path": "...", "model": "base", "language": "en", "device": "auto" }
GET    /api/transcribe/<run_id>
DELETE /api/transcribe/<run_id>
```

Both runners registered in `app/factory.py` alongside `DownloadRunner` and `JobManager`.

---

## Component 5 — Web UI Templates

Replace "Coming soon" placeholders in `extract-audio.html` and `transcribe.html` with simple forms + status polling, following the `download.html` pattern:

- `extract-audio.html`: one input (video file path), submit button, status display
- `transcribe.html`: video file path + model/language/device selectors, submit button, status display showing transcript text on completion

---

## File Layout (changes only)

```
link2video/
└── metadata_manager.py          ← new
└── metadata.py                  ← updated to delegate to MetadataManager

app/
├── audio_runner.py              ← new
├── transcribe_runner.py         ← new
├── factory.py                   ← register new runners
├── routes.py                    ← add /api/audio and /api/transcribe routes
└── templates/
    ├── extract-audio.html       ← replace placeholder
    └── transcribe.html          ← replace placeholder
```

No changes to `link2video/auto/extract_audio/` or `link2video/auto/transcribe/`.

---

## Error Handling

- `AudioRunner`: video file not found, FFmpeg not installed, extraction failure → status `failed` with error message
- `TranscribeRunner`: audio extraction failure propagates, Whisper not installed, model download failure, unsupported language/device → status `failed` with error message
- `MetadataManager`: file write failure → raises, caller sets status `failed`

---

## Success Criteria

1. Extract Audio tab: given a video path, produces `{stem}.mp3` alongside video and updates `{stem}.yaml` with `link2video/auto/extract` block
2. Transcribe tab: given a video path, auto-extracts audio if needed, produces transcript embedded in `{stem}.yaml` under `link2video/auto/transcribe`
3. Single `{stem}.yaml` per video accumulates metadata from all pipeline stages that have run
4. Existing processors (`ExtractAudioProcessor`, `TranscribeProcessor`) are not modified
5. Download metadata migrated to new unified format via MetadataManager
