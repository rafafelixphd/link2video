# Silence-Split Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the standalone `scripts/silence-split.py` into a modular, extensible `link2video/auto/split/silent/` package with multi-threaded cutting, progress feedback, and YAML metadata. Integrate into CLI as `link2video --auto silence-split`.

**Architecture:** Base abstract class (`SplitProcessor`) in `split/base.py` defines the interface. Silent splitter implementation in `split/silent/` with separate detector (ffmpeg parsing), cutter (multi-threaded), and metadata modules. CLI integration adds a new subcommand parser that instantiates `SilenceSplitter` and calls `.split()`.

**Tech Stack:** Python 3.8+, ffmpeg, threading, argparse, PyYAML

---

## File Structure

**New files to create:**
- `link2video/auto/__init__.py` — Package init
- `link2video/auto/split/__init__.py` — Exports `SplitProcessor`
- `link2video/auto/split/base.py` — Abstract base class
- `link2video/auto/split/silent/__init__.py` — Exports `SilenceSplitter`
- `link2video/auto/split/silent/detector.py` — Ffmpeg silence detection
- `link2video/auto/split/silent/cutter.py` — Multi-threaded segment cutting
- `link2video/auto/split/silent/metadata.py` — YAML metadata generation
- `tests/auto/test_silence_detector.py` — Detector unit tests
- `tests/auto/test_silence_metadata.py` — Metadata unit tests

**Files to modify:**
- `link2video/main.py` — Add `--auto` subcommand and `silence-split` handler

**Reference (read-only):**
- `scripts/silence-split.py` — Original script to extract logic from

---

## Tasks

### Task 1: Create Base Package Structure

**Files:**
- Create: `link2video/auto/__init__.py`
- Create: `link2video/auto/split/__init__.py`
- Create: `link2video/auto/split/base.py`

- [ ] **Step 1: Create auto package init**

Create `link2video/auto/__init__.py`:
```python
"""Automated video processing pipeline."""
```

- [ ] **Step 2: Create split package init and base class**

Create `link2video/auto/split/base.py`:
```python
from abc import ABC, abstractmethod
from typing import List, NamedTuple


class Segment(NamedTuple):
    """Represents a video segment."""
    segment_id: int
    start: float
    end: float
    filepath: str
    metadata_path: str


class SplitProcessor(ABC):
    """Abstract base class for video splitting strategies."""

    @abstractmethod
    def split(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        **kwargs
    ) -> List[Segment]:
        """
        Split video and return list of Segment objects.

        Args:
            input_file: Path to input video file.
            output_dir: Root directory where namespace folders are created.
            namespace: Folder name and filename prefix for outputs.
            **kwargs: Additional processor-specific arguments.

        Returns:
            List of Segment objects representing the split parts.
        """
        raise NotImplementedError
```

Create `link2video/auto/split/__init__.py`:
```python
from .base import SplitProcessor, Segment

__all__ = ["SplitProcessor", "Segment"]
```

- [ ] **Step 3: Commit**

```bash
git add link2video/auto/__init__.py link2video/auto/split/__init__.py link2video/auto/split/base.py
git commit -m "feat: add base SplitProcessor abstract class"
```

---

### Task 2: Implement Silence Detector

**Files:**
- Create: `link2video/auto/split/silent/detector.py`

- [ ] **Step 1: Write detector implementation**

Create `link2video/auto/split/silent/detector.py`:
```python
import subprocess
import re
import threading
import queue
from typing import Optional, Tuple


class SilenceDetector:
    """Detects silent gaps in video using ffmpeg silencedetect."""

    SENTINEL = None  # signals end of detection

    def __init__(
        self,
        input_file: str,
        noise: str = "-10dB",
        duration: float = 3.5,
        padding: float = 1.0,
    ):
        """
        Initialize silence detector.

        Args:
            input_file: Path to input video file.
            noise: Silence threshold in dB (e.g., "-10dB").
            duration: Minimum silence duration in seconds (default: 3.5).
            padding: Buffer zone around silence in seconds (default: 1.0).
        """
        self.input_file = input_file
        self.noise = noise
        self.duration = duration
        self.padding = padding

    def detect(self, q: queue.Queue) -> None:
        """
        Stream ffmpeg silencedetect output line by line.
        
        For each silence_end detected, push (cut_before, cut_after) to queue.
        
        Args:
            q: Queue to push silence pairs to.
        """
        cmd = [
            "ffmpeg",
            "-i",
            self.input_file,
            "-af",
            f"silencedetect=noise={self.noise}:d={self.duration}",
            "-f",
            "null",
            "-",
        ]
        proc = subprocess.Popen(cmd, stderr=subprocess.PIPE, text=True)

        pending_start = None

        for line in proc.stderr:
            # silence_start comes first
            m_start = re.search(r"silence_start: ([\d.]+)", line)
            if m_start:
                pending_start = float(m_start.group(1))
                continue

            # silence_end completes the pair
            m_end = re.search(r"silence_end: ([\d.]+)", line)
            if m_end and pending_start is not None:
                silence_end = float(m_end.group(1))
                # Apply padding: cut_before moves into silence, cut_after moves into silence
                cut_before = pending_start + self.padding
                cut_after = silence_end - self.padding
                q.put((cut_before, cut_after))
                pending_start = None

        proc.wait()
        q.put(self.SENTINEL)

    def spawn_detector_thread(self, q: queue.Queue) -> threading.Thread:
        """Spawn detector thread and return it."""
        detector_thread = threading.Thread(
            target=self.detect,
            args=(q,),
            daemon=True,
        )
        detector_thread.start()
        return detector_thread
```

- [ ] **Step 2: Test detector with mock ffmpeg output**

Create `tests/auto/test_silence_detector.py`:
```python
import queue
import threading
from unittest.mock import patch, MagicMock
import pytest

from link2video.auto.split.silent.detector import SilenceDetector


def test_detector_parses_silence_pairs():
    """Test that detector correctly parses silence_start and silence_end."""
    mock_ffmpeg_output = [
        "[silencedetect @ 0x...] silence_start: 0.5\n",
        "[silencedetect @ 0x...] silence_end: 3.2\n",
        "[silencedetect @ 0x...] silence_start: 10.1\n",
        "[silencedetect @ 0x...] silence_end: 12.5\n",
    ]

    detector = SilenceDetector("dummy.mp4", padding=1.0)
    q = queue.Queue()

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stderr = iter(mock_ffmpeg_output)
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        detector.detect(q)

    # Read results from queue
    results = []
    while True:
        item = q.get()
        if item is SilenceDetector.SENTINEL:
            break
        results.append(item)

    assert len(results) == 2
    assert results[0] == (0.5 + 1.0, 3.2 - 1.0)  # (1.5, 2.2)
    assert results[1] == (10.1 + 1.0, 12.5 - 1.0)  # (11.1, 11.5)


def test_detector_applies_padding():
    """Test that padding is correctly applied to silence boundaries."""
    detector = SilenceDetector("dummy.mp4", padding=0.5)
    
    # Mock ffmpeg output with a single silence
    mock_ffmpeg_output = [
        "[silencedetect @ 0x...] silence_start: 10.0\n",
        "[silencedetect @ 0x...] silence_end: 15.0\n",
    ]

    q = queue.Queue()

    with patch("subprocess.Popen") as mock_popen:
        mock_proc = MagicMock()
        mock_proc.stderr = iter(mock_ffmpeg_output)
        mock_proc.wait = MagicMock()
        mock_popen.return_value = mock_proc

        detector.detect(q)

    result = q.get()
    assert result == (10.5, 14.5)  # (10 + 0.5, 15 - 0.5)
```

- [ ] **Step 3: Run tests to verify**

```bash
pytest tests/auto/test_silence_detector.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add link2video/auto/split/silent/detector.py tests/auto/test_silence_detector.py
git commit -m "feat: implement silence detector with padding"
```

---

### Task 3: Implement Metadata Generator

**Files:**
- Create: `link2video/auto/split/silent/metadata.py`

- [ ] **Step 1: Get video FPS extraction utility**

Create `link2video/auto/split/silent/metadata.py`:
```python
import subprocess
import json
import yaml
import os
from pathlib import Path
from typing import Optional


class MetadataGenerator:
    """Generates YAML metadata for video segments."""

    def __init__(self, input_file: str):
        """
        Initialize metadata generator.

        Args:
            input_file: Path to input video file.
        """
        self.input_file = input_file
        self._fps = None

    def get_fps(self) -> float:
        """
        Extract FPS from input video using ffprobe.

        Returns:
            Frames per second as a float.

        Raises:
            RuntimeError: If FPS cannot be extracted.
        """
        if self._fps is not None:
            return self._fps

        cmd = [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=r_frame_rate",
            "-of",
            "json",
            self.input_file,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        data = json.loads(result.stdout)

        if not data.get("streams"):
            raise RuntimeError(f"Could not extract FPS from {self.input_file}")

        frame_rate_str = data["streams"][0]["r_frame_rate"]
        num, denom = frame_rate_str.split("/")
        self._fps = float(num) / float(denom)
        return self._fps

    def frame_from_timestamp(self, timestamp: float) -> int:
        """
        Calculate frame number from timestamp.

        Args:
            timestamp: Time in seconds.

        Returns:
            Frame number (integer).
        """
        fps = self.get_fps()
        return int(timestamp * fps)

    def write_metadata(
        self,
        segment_id: int,
        original_file: str,
        start: float,
        end: float,
        output_path: str,
    ) -> None:
        """
        Write YAML metadata file for a segment.

        Args:
            segment_id: Segment number.
            original_file: Path to original input video.
            start: Start time in seconds.
            end: End time in seconds.
            output_path: Path where metadata file should be written.
        """
        fps = self.get_fps()
        start_frame = self.frame_from_timestamp(start)
        end_frame = self.frame_from_timestamp(end)

        metadata = {
            "name": f"segment_{segment_id:03d}",
            "original_file": original_file,
            "fps": round(fps, 2),
            "start": round(start, 2),
            "end": round(end, 2),
            "start_frame": start_frame,
            "end_frame": end_frame,
        }

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False)
```

- [ ] **Step 2: Write metadata unit tests**

Create `tests/auto/test_silence_metadata.py`:
```python
import tempfile
import yaml
import pytest
from pathlib import Path
from unittest.mock import patch

from link2video.auto.split.silent.metadata import MetadataGenerator


def test_frame_from_timestamp():
    """Test frame calculation from timestamp."""
    with patch.object(MetadataGenerator, "get_fps", return_value=29.97):
        gen = MetadataGenerator("dummy.mp4")
        
        # At 1 second with 29.97 fps, should be frame 29-30
        frame = gen.frame_from_timestamp(1.0)
        assert frame == 29
        
        # At 10 seconds, should be frame ~299
        frame = gen.frame_from_timestamp(10.0)
        assert frame == 299


def test_write_metadata_creates_yaml():
    """Test that metadata is written as valid YAML."""
    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.object(MetadataGenerator, "get_fps", return_value=30.0):
            gen = MetadataGenerator("input.mp4")
            
            output_path = Path(tmpdir) / "segment_001.yaml"
            gen.write_metadata(
                segment_id=1,
                original_file="input.mp4",
                start=0.0,
                end=31.2,
                output_path=str(output_path),
            )

            assert output_path.exists()
            
            with open(output_path) as f:
                data = yaml.safe_load(f)
            
            assert data["name"] == "segment_001"
            assert data["original_file"] == "input.mp4"
            assert data["fps"] == 30.0
            assert data["start"] == 0.0
            assert data["end"] == 31.2
            assert data["start_frame"] == 0
            assert data["end_frame"] == 936  # 31.2 * 30
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/auto/test_silence_metadata.py -v
```

Expected: PASS (2 passed)

- [ ] **Step 4: Commit**

```bash
git add link2video/auto/split/silent/metadata.py tests/auto/test_silence_metadata.py
git commit -m "feat: implement metadata generator with FPS extraction"
```

---

### Task 4: Implement Multi-Threaded Cutter

**Files:**
- Create: `link2video/auto/split/silent/cutter.py`

- [ ] **Step 1: Write cutter implementation**

Create `link2video/auto/split/silent/cutter.py`:
```python
import subprocess
import os
import threading
import queue
import sys
from typing import Callable, Optional

from .metadata import MetadataGenerator


class SegmentCutter:
    """Multi-threaded video segment cutter with progress display."""

    def __init__(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        metadata_gen: MetadataGenerator,
        num_threads: int = 2,
        min_segment: float = 3.0,
    ):
        """
        Initialize segment cutter.

        Args:
            input_file: Path to input video.
            output_dir: Root output directory.
            namespace: Namespace/folder name for segments.
            metadata_gen: MetadataGenerator instance.
            num_threads: Number of cutting worker threads (default: 2).
            min_segment: Minimum segment duration in seconds (default: 3.0).
        """
        self.input_file = input_file
        self.output_dir = output_dir
        self.namespace = namespace
        self.metadata_gen = metadata_gen
        self.num_threads = num_threads
        self.min_segment = min_segment
        
        self.namespace_dir = os.path.join(output_dir, namespace)
        self.ext = os.path.splitext(input_file)[1] or ".mp4"
        
        self.total_segments = 0
        self.segments_cut = 0
        self.lock = threading.Lock()

    def _cut_segment(
        self,
        segment_id: int,
        start: float,
        end: float,
    ) -> bool:
        """
        Cut a single segment using ffmpeg.

        Args:
            segment_id: Segment number.
            start: Start time in seconds.
            end: End time in seconds.

        Returns:
            True if successful, False otherwise.
        """
        os.makedirs(self.namespace_dir, exist_ok=True)
        
        segment_name = f"segment_{segment_id:03d}"
        out_path = os.path.join(self.namespace_dir, f"{segment_name}{self.ext}")
        metadata_path = os.path.join(self.namespace_dir, f"{segment_name}.yaml")

        cmd = [
            "ffmpeg",
            "-i",
            self.input_file,
            "-ss",
            str(start),
            "-to",
            str(end),
            "-c",
            "copy",
            "-avoid_negative_ts",
            "make_zero",
            out_path,
            "-y",
        ]
        
        try:
            subprocess.run(cmd, capture_output=True, check=True)
            self.metadata_gen.write_metadata(
                segment_id=segment_id,
                original_file=self.input_file,
                start=start,
                end=end,
                output_path=metadata_path,
            )
            return True
        except subprocess.CalledProcessError:
            return False

    def _worker(self, job_queue: queue.Queue) -> None:
        """
        Worker thread that processes cutting jobs.

        Args:
            job_queue: Queue of (segment_id, start, end) tuples.
        """
        while True:
            job = job_queue.get()
            if job is None:  # SENTINEL
                break

            segment_id, start, end = job
            success = self._cut_segment(segment_id, start, end)

            with self.lock:
                self.segments_cut += 1
                status = "✓" if success else "✗"
                print(
                    f"  [{self.segments_cut}/{self.total_segments}] "
                    f"Cutting segment_{segment_id:03d}.mp4... {status}"
                )

    def cut_segments(self, segments: list) -> None:
        """
        Cut multiple segments using a worker pool.

        Args:
            segments: List of (start, end) tuples to cut.
        """
        self.total_segments = len(segments)
        self.segments_cut = 0
        
        print(f"Cutting segments ({self.num_threads} workers):")
        
        job_queue = queue.Queue()
        
        # Spawn worker threads
        workers = []
        for _ in range(self.num_threads):
            t = threading.Thread(target=self._worker, args=(job_queue,), daemon=True)
            t.start()
            workers.append(t)
        
        # Queue all cutting jobs
        for segment_id, (start, end) in enumerate(segments, 1):
            job_queue.put((segment_id, start, end))
        
        # Send SENTINEL to stop workers
        for _ in range(self.num_threads):
            job_queue.put(None)
        
        # Wait for all workers to finish
        for t in workers:
            t.join()
```

- [ ] **Step 2: Commit**

```bash
git add link2video/auto/split/silent/cutter.py
git commit -m "feat: implement multi-threaded segment cutter"
```

---

### Task 5: Create SilenceSplitter (Main Class)

**Files:**
- Create: `link2video/auto/split/silent/__init__.py`

- [ ] **Step 1: Write SilenceSplitter class**

Create `link2video/auto/split/silent/__init__.py`:
```python
import os
import queue
from typing import List

from link2video.auto.split.base import SplitProcessor, Segment
from .detector import SilenceDetector
from .cutter import SegmentCutter
from .metadata import MetadataGenerator


class SilenceSplitter(SplitProcessor):
    """Split video at silent gaps using ffmpeg silencedetect."""

    def __init__(self):
        pass

    def split(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        noise: str = "-10dB",
        silence_duration: float = 3.5,
        padding: float = 1.0,
        threads: int = 2,
        min_segment: float = 3.0,
        dry_run: bool = False,
    ) -> List[Segment]:
        """
        Split video at silent gaps.

        Args:
            input_file: Path to input video file.
            output_dir: Root output directory.
            namespace: Namespace folder name.
            noise: Silence threshold in dB (default: "-10dB").
            silence_duration: Minimum silence duration in seconds (default: 3.5).
            padding: Padding around silence boundaries in seconds (default: 1.0).
            threads: Number of cutting worker threads (default: 2).
            min_segment: Minimum segment duration in seconds (default: 3.0).
            dry_run: If True, only preview without creating files.

        Returns:
            List of Segment objects.
        """
        detector = SilenceDetector(
            input_file=input_file,
            noise=noise,
            duration=silence_duration,
            padding=padding,
        )
        metadata_gen = MetadataGenerator(input_file)
        cutter = SegmentCutter(
            input_file=input_file,
            output_dir=output_dir,
            namespace=namespace,
            metadata_gen=metadata_gen,
            num_threads=threads,
            min_segment=min_segment,
        )

        # Spawn detector thread
        q = queue.Queue()
        detector_thread = detector.spawn_detector_thread(q)

        # Process silence pairs and build segment list
        segments = []
        segment_id = 0
        prev_end = 0.0
        
        print(f"Detecting silences (threshold={noise}, min gap={silence_duration}s)...\n")

        while True:
            item = q.get()

            if item is SilenceDetector.SENTINEL:
                # Add final segment from last cut point to end
                if prev_end < float("inf"):
                    segment_id += 1
                    if not dry_run:
                        # Get video duration to know where to stop
                        import subprocess
                        import json
                        cmd = [
                            "ffprobe",
                            "-v",
                            "error",
                            "-show_entries",
                            "format=duration",
                            "-of",
                            "json",
                            input_file,
                        ]
                        result = subprocess.run(cmd, capture_output=True, text=True)
                        duration = float(json.loads(result.stdout)["format"]["duration"])
                        
                        if dry_run:
                            print(f"  Segment {segment_id}: {prev_end:.2f}s → EOF")
                        else:
                            segments.append((prev_end, duration))
                            print(f"  Segment {segment_id}: {prev_end:.2f}s → EOF ({duration - prev_end:.1f}s)")
                break

            cut_before, cut_after = item
            seg_length = cut_before - prev_end

            if seg_length >= min_segment:
                segment_id += 1
                if dry_run:
                    print(f"  Segment {segment_id}: {prev_end:.2f}s → {cut_before:.2f}s ({seg_length:.1f}s)")
                else:
                    segments.append((prev_end, cut_before))
                    print(f"  Segment {segment_id}: {prev_end:.2f}s → {cut_before:.2f}s ({seg_length:.1f}s)")
            else:
                print(f"  Skipping {prev_end:.2f}s → {cut_before:.2f}s ({seg_length:.1f}s < {min_segment}s)")

            prev_end = cut_after

        detector_thread.join()

        # Cut segments if not dry-run
        output_segments = []
        if not dry_run and segments:
            print()
            cutter.cut_segments(segments)
            
            # Build Segment objects
            for i, (start, end) in enumerate(segments, 1):
                segment_name = f"segment_{i:03d}"
                ext = os.path.splitext(input_file)[1] or ".mp4"
                filepath = os.path.join(output_dir, namespace, f"{segment_name}{ext}")
                metadata_path = os.path.join(output_dir, namespace, f"{segment_name}.yaml")
                output_segments.append(
                    Segment(
                        segment_id=i,
                        start=start,
                        end=end,
                        filepath=filepath,
                        metadata_path=metadata_path,
                    )
                )
            
            print(f"\nDone — {len(output_segments)} segments saved to {output_dir}/{namespace}/")

        return output_segments


__all__ = ["SilenceSplitter"]
```

- [ ] **Step 2: Commit**

```bash
git add link2video/auto/split/silent/__init__.py
git commit -m "feat: implement SilenceSplitter main class"
```

---

### Task 6: Integrate into CLI

**Files:**
- Modify: `link2video/main.py`

- [ ] **Step 1: Add silence-split subcommand to main.py**

Modify `link2video/main.py` to add the following at the top of the file (after imports):

```python
from link2video.auto.split.silent import SilenceSplitter
```

And modify the `main()` function. Replace the current `@Gooey` decorator with a new approach that handles both GUI and CLI modes:

```python
def main():
    """
    Main entry point supporting both GUI (default) and CLI modes.
    
    GUI mode (default): Multi-platform Video Downloader with Gooey
    CLI mode (--auto): Automated processing commands (silence-split, etc.)
    """
    parser = argparse.ArgumentParser(
        description="link2video - Video processing suite"
    )
    
    # Top-level subparser for modes
    subparsers = parser.add_subparsers(dest="mode", help="Operation mode")
    
    # GUI mode (default) - download videos
    gui_parser = subparsers.add_parser("download", help="Download videos (GUI)")
    
    # CLI mode - automated processing
    auto_parser = subparsers.add_parser("--auto", help="Automated processing")
    auto_subparsers = auto_parser.add_subparsers(dest="auto_command", help="Processing command")
    
    # silence-split subcommand
    silence_split_parser = auto_subparsers.add_parser(
        "silence-split",
        help="Split video at silent gaps"
    )
    silence_split_parser.add_argument(
        "input",
        help="Input video file path"
    )
    silence_split_parser.add_argument(
        "--namespace",
        required=True,
        help="Output folder and filename prefix (e.g., 'my-project' creates {output_dir}/my-project/segment_001.mp4)"
    )
    silence_split_parser.add_argument(
        "--output-dir",
        default="segments",
        help="Root directory for output segments (default: segments)"
    )
    silence_split_parser.add_argument(
        "--noise",
        default="-10dB",
        help="Silence detection threshold in dB. Lower (more negative) values detect quieter silences. Increase this to ignore background noise (default: -10dB)"
    )
    silence_split_parser.add_argument(
        "--silence-duration",
        type=float,
        default=3.5,
        help="Minimum duration of silence in seconds to count as a split point. Increase this to ignore brief pauses within sentences like breathing or hesitation (default: 3.5)"
    )
    silence_split_parser.add_argument(
        "--padding",
        type=float,
        default=1.0,
        help="Buffer zone in seconds on both sides of detected silence boundaries. Prevents cutting too close to the end of one sentence or the beginning of the next. Increase if speech is being cut off at segment edges (default: 1.0)"
    )
    silence_split_parser.add_argument(
        "--threads",
        type=int,
        default=2,
        help="Number of parallel worker threads for cutting segments. Increase on high-performance systems for faster processing (default: 2)"
    )
    silence_split_parser.add_argument(
        "--min-segment",
        type=float,
        default=3.0,
        help="Minimum segment duration in seconds. Shorter segments are automatically discarded. Increase this to ensure meaningful content in each segment (default: 3.0)"
    )
    silence_split_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview planned segments without cutting or creating files. Useful for tuning parameters before committing"
    )
    
    args = parser.parse_args()
    
    # Handle CLI mode (--auto commands)
    if args.mode == "--auto":
        if args.auto_command == "silence-split":
            _handle_silence_split(args)
            return
    
    # Fall back to GUI mode for backward compatibility
    _run_gui_downloader(args)


def _handle_silence_split(args):
    """Handle the silence-split command."""
    import os
    
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)
    
    splitter = SilenceSplitter()
    
    try:
        segments = splitter.split(
            input_file=args.input,
            output_dir=args.output_dir,
            namespace=args.namespace,
            noise=args.noise,
            silence_duration=args.silence_duration,
            padding=args.padding,
            threads=args.threads,
            min_segment=args.min_segment,
            dry_run=args.dry_run,
        )
        
        if args.dry_run:
            print("\n(Preview mode — no files were created)")
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _run_gui_downloader(args):
    """Run the GUI downloader (original Gooey interface)."""
    from gooey import Gooey, GooeyParser
    from .platform_detector import detect_platform
    from .config import get_default_download_path
    
    # Rerun with Gooey decorator for GUI
    @Gooey(
        program_name="Multi-Platform Video Downloader",
        default_size=(700, 600),
        richtext_controls=True,
        navigation='TABBED',
        body_bg_color='#2b2b2b',
        footer_bg_color='#2b2b2b',
        sidebar_bg_color='#1e1e1e',
        richtext_bg_color='#1e1e1e'
    )
    def gui_main():
        parser = GooeyParser(
            description="Download videos from Instagram, YouTube, and LinkedIn with automatic platform detection and metadata creation"
        )
        
        try:
            default_path = get_default_download_path()
        except Exception:
            default_path = os.path.expanduser("~/Movies")
        
        parser.add_argument(
            'url',
            metavar='Video URL',
            help="Enter the URL of the video (Instagram, YouTube, or LinkedIn)",
            widget='TextField',
            gooey_options={'columns': 2, 'full_width': True}
        )
        parser.add_argument(
            'save_path',
            metavar='Save Directory',
            help="Select the directory to save the video",
            widget='DirChooser',
            gooey_options={'columns': 2, 'default': default_path},
            default=default_path
        )
        parser.add_argument(
            '--tags',
            metavar='Tags (optional)',
            help="Comma-separated tags for categorization (e.g., tutorial, funny, important)",
            default='',
            widget='TextField',
            gooey_options={'columns': 2, 'full_width': True}
        )
        parser.add_argument(
            '--comments',
            metavar='Comments/Notes (optional)',
            help="Additional notes or comments about this video",
            default='',
            widget='Textarea',
            gooey_options={'columns': 2, 'full_width': True, 'height': 100}
        )
        
        gui_args = parser.parse_args()
        
        if not gui_args.url or not gui_args.url.strip():
            print("Error: URL cannot be empty")
            return
        
        if not gui_args.save_path or not gui_args.save_path.strip():
            print("Error: Save directory cannot be empty")
            return
        
        tags = []
        if gui_args.tags and gui_args.tags.strip():
            tags = [tag.strip() for tag in gui_args.tags.split(',') if tag.strip()]
        
        comments = gui_args.comments.strip() if gui_args.comments else ""
        
        try:
            downloader = detect_platform(gui_args.url)
            success, result = downloader.download(
                url=gui_args.url,
                save_path=gui_args.save_path,
                tags=tags,
                comments=comments
            )
            
            if success:
                filepath = result
                filename = os.path.basename(filepath)
                print(f"✓ Downloaded Successfully: {filename}")
                print(f"  Location: {filepath}")
                if tags:
                    print(f"  Tags: {', '.join(tags)}")
                if comments:
                    print(f"  Notes: {comments}")
                print(f"\nMetadata file created: {os.path.dirname(filepath)}/metadata/")
            else:
                print(f"Error: {result}")
        
        except Exception as e:
            print(f"Unexpected Error: {str(e)}")
            import traceback
            traceback.print_exc()
    
    gui_main()
```

- [ ] **Step 2: Add imports at the top of main.py**

Ensure these imports are present:
```python
import argparse
import os
import sys
from link2video.auto.split.silent import SilenceSplitter
```

- [ ] **Step 3: Test CLI help**

```bash
python -m link2video --auto silence-split --help
```

Expected output: Help text for silence-split with all parameters and descriptions.

- [ ] **Step 4: Commit**

```bash
git add link2video/main.py
git commit -m "feat: integrate silence-split into CLI with --auto subcommand"
```

---

### Task 7: Create Tests Directory Structure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/auto/__init__.py`

- [ ] **Step 1: Create test package structure**

```bash
mkdir -p tests/auto
touch tests/__init__.py tests/auto/__init__.py
```

- [ ] **Step 2: Commit**

```bash
git add tests/__init__.py tests/auto/__init__.py
git commit -m "chore: create tests directory structure"
```

---

### Task 8: Manual Testing with Real Video

**Files:** (no new files)

- [ ] **Step 1: Test dry-run mode**

```bash
python -m link2video --auto silence-split sample.mp4 \
  --namespace test-run \
  --output-dir ./test-output \
  --silence-duration 3.5 \
  --padding 1.0 \
  --dry-run
```

Expected: Preview of segments without creating files.

- [ ] **Step 2: Test actual cutting**

```bash
python -m link2video --auto silence-split sample.mp4 \
  --namespace test-run \
  --output-dir ./test-output \
  --silence-duration 3.5 \
  --padding 1.0 \
  --threads 2
```

Expected: Segments created in `./test-output/test-run/`

- [ ] **Step 3: Verify output structure**

```bash
ls -la test-output/test-run/
```

Expected:
```
segment_001.mp4
segment_001.yaml
segment_002.mp4
segment_002.yaml
...
```

- [ ] **Step 4: Verify YAML metadata**

```bash
cat test-output/test-run/segment_001.yaml
```

Expected:
```yaml
name: segment_001
original_file: sample.mp4
fps: 29.97
start: 0.0
end: 31.2
start_frame: 0
end_frame: 936
```

- [ ] **Step 5: Test with different padding values**

```bash
python -m link2video --auto silence-split sample.mp4 \
  --namespace test-run-padded \
  --output-dir ./test-output \
  --silence-duration 3.5 \
  --padding 0.5 \
  --threads 2
```

Expected: Different segment boundaries than the 1.0s padding test.

- [ ] **Step 6: Verify multi-threading works**

```bash
python -m link2video --auto silence-split sample.mp4 \
  --namespace test-run-threaded \
  --output-dir ./test-output \
  --silence-duration 3.5 \
  --padding 1.0 \
  --threads 4
```

Expected: Progress display shows "4 workers" cutting in parallel.

- [ ] **Step 7: Clean up test artifacts**

```bash
rm -rf test-output/
```

---

## Spec Compliance Checklist

- [x] **Architecture:** Base class in `split/base.py`, silent module in `split/silent/`
- [x] **Detector:** Silence detection with configurable padding (default 1.0s)
- [x] **Cutter:** Multi-threaded cutting (default 2 threads, configurable)
- [x] **Metadata:** YAML with fps, frame numbers, timestamps
- [x] **Progress Display:** Real-time status during detection and cutting
- [x] **Default Parameters:** silence_duration=3.5s (updated from 2s), padding=1.0s
- [x] **CLI Integration:** `link2video --auto silence-split` with all parameters
- [x] **Parameter Help Text:** Clear English descriptions for all CLI arguments
- [x] **Namespace Support:** `{namespace}/segment_{id}.mp4` and `{namespace}/segment_{id}.yaml`
- [x] **Extensibility:** Base class allows future processors (transcript, scene detection, etc.)

No gaps identified. All requirements covered.
