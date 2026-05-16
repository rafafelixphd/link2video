# Silence-Split Video Processor

## Quick Start

```bash
link2video --auto silence-split input.mp4 \
  --namespace my-project \
  --output-dir ./segments
```

## Command Syntax

```bash
link2video --auto silence-split <input_file> \
  --namespace <name> \
  [--output-dir <dir>] \
  [--noise <dB>] \
  [--silence-duration <seconds>] \
  [--padding <seconds>] \
  [--threads <count>] \
  [--min-segment <seconds>] \
  [--dry-run]
```

## Required Arguments

| Argument      | Description                               |
| ------------- | ----------------------------------------- |
| `input_file`  | Path to video file to process             |
| `--namespace` | Output folder and segment filename prefix |

## Optional Arguments

| Argument             | Default    | Description                                                       |
| -------------------- | ---------- | ----------------------------------------------------------------- |
| `--output-dir`       | `segments` | Root directory for output folders                                 |
| `--noise`            | `-10dB`    | Silence detection threshold (lower = more sensitive)              |
| `--silence-duration` | `3.5`      | Min silence length in seconds to trigger split                    |
| `--padding`          | `1.0`      | Buffer zone around silence boundaries (prevents cutting mid-word) |
| `--threads`          | `2`        | Parallel worker threads for cutting segments                      |
| `--min-segment`      | `3.0`      | Minimum segment duration in seconds (shorter ones discarded)      |
| `--dry-run`          | —          | Preview segments without creating files                           |

## Examples

**Preview segments before cutting:**

```bash
link2video --auto silence-split speech.mp4 \
  --namespace my-talk \
  --dry-run
```

**Split with custom silence threshold (more strict):**

```bash
link2video --auto silence-split interview.mp4 \
  --namespace interview-segments \
  --silence-duration 5.0 \
  --padding 0.5
```

**Faster processing with more threads:**

```bash
link2video --auto silence-split long-video.mp4 \
  --namespace parts \
  --threads 4
```

## Output Structure

```
segments/
└── my-project/
    ├── segment_001.mp4
    ├── segment_001.yaml
    ├── segment_002.mp4
    ├── segment_002.yaml
    └── ...
```

## Metadata File Format

Each `.yaml` file contains:

```yaml
name: segment_001
original_file: input.mp4
fps: 29.97
start: 0.0
end: 31.2
start_frame: 0
end_frame: 936
```

## Tuning Parameters

**Getting too many short segments?**

- Increase `--silence-duration` (e.g., 4.0 or 5.0)
- Increase `--min-segment`

**Speech being cut off at edges?**

- Increase `--padding` (e.g., 1.5 or 2.0)

**Detecting background noise as silence?**

- Increase `--noise` toward 0 (e.g., -5dB instead of -10dB)

**Too slow?**

- Increase `--threads` (depends on CPU cores)

## Exit Codes

| Code | Meaning                            |
| ---- | ---------------------------------- |
| 0    | Success                            |
| 1    | File not found or processing error |

## Notes

- Segments are cut using stream copy (no re-encoding) — very fast
- FFmpeg must be installed and in PATH
- Output directory is created if it doesn't exist
