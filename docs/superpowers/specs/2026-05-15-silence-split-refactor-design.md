# Silence-Based Video Splitting Module Design

**Date:** 2026-05-15  
**Status:** Approved  
**Scope:** Refactor and integrate silence-detection video splitting into `link2video` CLI with multi-threaded cutting, better progress visibility, and extensible plugin architecture.

---

## Overview

Transform the existing `scripts/silence-split.py` standalone script into a modular, reusable package within `link2video` that:
- Detects silent gaps in video and splits at those boundaries
- Adds configurable padding to avoid cutting at speech edges
- Cuts segments in parallel using worker threads
- Generates YAML metadata for each segment (timestamps, frame numbers, FPS)
- Provides real-time progress feedback during detection and cutting
- Serves as the foundation for future processors (transcript-based splitting, scene detection, etc.)

---

## Architecture

### Directory Structure

```
link2video/
  auto/
    __init__.py
    split/
      __init__.py          # exports SplitProcessor base
      base.py              # abstract base class for all splitters
      silent/
        __init__.py        # exports SilenceSplitter
        detector.py        # ffmpeg silence detection + parsing
        cutter.py          # multi-threaded segment cutting + progress
        metadata.py        # YAML metadata generation
```

### Base Class Design

**`split/base.py`** — Abstract `SplitProcessor`

Defines the contract for all splitting strategies:

```python
class SplitProcessor:
    def split(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        **kwargs
    ) -> List[Segment]:
        """
        Split video and return list of Segment objects.
        Implementations handle their own threading, progress, and output.
        """
        raise NotImplementedError
```

This ensures future processors (transcript-based, duration-based, etc.) follow the same interface.

---

## Silent Splitter Implementation

### Component: `detector.py`

**Responsibility:** Stream ffmpeg silencedetect output, parse silence pairs, apply padding, yield cut points.

**Key behavior:**
- Runs ffmpeg silencedetect in a producer thread
- Streams output line-by-line (not waiting for full scan to complete)
- Parses `silence_start` and `silence_end` timestamps from ffmpeg stderr
- Applies configurable padding:
  - `cut_before = silence_start + padding_seconds`
  - `cut_after = silence_end - padding_seconds`
- Yields silence pairs to a queue as they're detected (producer-consumer pattern)

**Parameters:**
- `noise`: Silence threshold in dB (default: `-10dB`)
- `duration`: Minimum silence duration in seconds (default: `3.5`)
- `padding`: Buffer zone around silence boundaries in seconds (default: `1.0`)

### Component: `cutter.py`

**Responsibility:** Multi-threaded segment cutting with real-time progress display.

**Key behavior:**
- Spawns N worker threads (default: 2, configurable) to cut video segments
- Each worker consumes segment jobs from a queue (from detector)
- Runs ffmpeg with `-ss` (start) and `-to` (end) flags, stream copy mode (no re-encoding)
- Displays real-time progress:
  ```
  Cutting segments (2 workers):
    [1/25] Cutting segment_001.mp4... ✓
    [2/25] Cutting segment_002.mp4... (in progress)
    [3/25] Waiting...
  ```
- Calls `metadata.py` to write YAML for each segment immediately after cutting

**Parameters:**
- `threads`: Number of parallel cutting workers (default: `2`)
- `min_segment`: Minimum segment duration in seconds; shorter segments are discarded (default: `3.0`)

### Component: `metadata.py`

**Responsibility:** Generate YAML metadata files for each segment.

**Output format:**
```yaml
name: segment_001
original_file: input.mp4
fps: 29.97
start: 0.0
end: 31.2
start_frame: 0
end_frame: 936
```

**Calculation:**
- `fps`: Extracted from input video once at start
- `start_frame` and `end_frame`: Calculated from timestamps and FPS (`frame = timestamp * fps`)

---

## CLI Integration

### Subcommand: `link2video --auto silence-split`

**Full command:**
```bash
link2video --auto silence-split input.mp4 \
  --namespace my-project \
  --output-dir ./segments \
  --noise -10dB \
  --silence-duration 3.5 \
  --padding 1.0 \
  --threads 2 \
  --min-segment 3.0 \
  --dry-run
```

### Parameter Descriptions

| Parameter | Default | Description |
|-----------|---------|-------------|
| `input` | (required) | Path to input video file |
| `--namespace` | (required) | Folder name and filename prefix for output segments. Outputs to `{output_dir}/{namespace}/segment_001.mp4` |
| `--output-dir` | `./segments` | Root directory where namespace folders are created |
| `--noise` | `-10dB` | Silence detection threshold in dB. Lower values (more negative) detect quieter silences. Increase this to ignore background noise. |
| `--silence-duration` | `3.5` | Minimum duration of silence in seconds to count as a split point. Increase this to ignore brief pauses within sentences (e.g., breathing, hesitation). |
| `--padding` | `1.0` | Buffer zone in seconds on both sides of detected silence boundaries. Prevents cutting too close to the end of one sentence or the beginning of the next. Increase if speech is being cut off at segment edges. |
| `--threads` | `2` | Number of parallel worker threads for cutting segments. Increase on high-performance systems for faster processing. |
| `--min-segment` | `3.0` | Minimum segment duration in seconds. Shorter segments are automatically discarded. Increase this to ensure meaningful content in each segment. |
| `--dry-run` | (flag) | Preview all planned segments without actually cutting or creating files. Useful for tuning parameters before committing. |

---

## Data Flow

1. **Initialization:**
   - Extract FPS from input video
   - Spawn detector thread (runs ffmpeg silencedetect)

2. **Detection Phase:**
   - Detector thread streams ffmpeg output, parses silence pairs
   - For each detected silence: calculate padded cut points, push to queue
   - Display: `Detecting silences... [████░░░░░] 40%`

3. **Cutting Phase:**
   - Cutter thread spawns N worker threads
   - Workers consume cut jobs from queue in parallel
   - Each worker: runs ffmpeg to extract segment, writes YAML metadata
   - Display: `[1/25] Cutting segment_001.mp4... ✓`

4. **Completion:**
   - All segments written to `{output_dir}/{namespace}/`
   - Summary: `Done — 25 segments saved to ./segments/my-project/`

---

## Configuration Defaults (Updated from Original)

| Setting | Previous | New | Rationale |
|---------|----------|-----|-----------|
| Silence duration | 2.0s | 3.5s | Reduces false splits on brief pauses; more stable for natural speech |
| Padding | (none) | 1.0s | Prevents cutting at speech boundaries; configurable for fine-tuning |
| Output format | `segment_NNN.mp4` | `{namespace}/segment_{id}.mp4` | Organized namespace support for batch processing |
| Metadata | (none) | YAML with fps, frame numbers | Enables downstream processing and timeline reconstruction |
| Threading | Serial cutting | 2 parallel workers | Faster processing without overwhelming system |

---

## Error Handling

- **Missing input file:** Exit with clear error message before starting detection
- **Invalid video format:** Caught by ffmpeg; display error and exit
- **Insufficient disk space:** Caught by ffmpeg during cutting; display error and continue
- **Silent entire video:** Detector reports 0 segments; user should adjust threshold

---

## Testing Strategy

1. **Unit tests:**
   - Silence detector: mock ffmpeg output, verify padding calculations
   - Metadata writer: verify YAML structure and frame number calculations
   - Base class: verify interface contract

2. **Integration tests:**
   - End-to-end: real video files with known silence patterns
   - CLI argument parsing and defaults
   - Output structure and file creation

3. **Manual testing:**
   - Real speech videos with different silence patterns
   - Parameter tuning (--silence-duration, --padding) effects
   - Multi-threaded cutting under load

---

## Future Extensions

This design accommodates future processors:

- **Transcript-based splitter:** Split at sentence/paragraph boundaries from a transcript
- **Scene detection splitter:** Split at scene cuts (ffmpeg scene detect filter)
- **Duration-based splitter:** Split into fixed-length chunks
- **Combined splitters:** Apply multiple strategies sequentially

Each would inherit from `SplitProcessor` and follow the same interface.

---

## Success Criteria

- ✅ Silence detection with configurable padding works correctly
- ✅ Default silence duration (3.5s) reduces false positives vs. original 2.0s
- ✅ Multi-threaded cutting is visibly faster than serial cutting
- ✅ Progress display shows real-time status during detection and cutting
- ✅ YAML metadata includes fps and frame numbers
- ✅ CLI integration with `link2video --auto silence-split` works smoothly
- ✅ Module can be extended for future processors without modification
