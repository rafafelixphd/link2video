"""SilenceSplitter: Main orchestrator for silence-based video splitting."""

import json
import queue
import subprocess
from typing import List

from ..base import SplitProcessor, Segment
from .detector import SilenceDetector
from .cutter import SegmentCutter
from .metadata import MetadataGenerator


class SilenceSplitter(SplitProcessor):
    """
    Main orchestrator for splitting videos by silence detection.

    Coordinates the silence detection → segment cutting → metadata generation workflow.
    Uses a producer/consumer pattern with queues for efficient processing.
    """

    def __init__(self):
        """Initialize the SilenceSplitter. No setup required."""
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
        dry_run: bool = False
    ) -> List[Segment]:
        """
        Split a video into segments based on silence detection.

        Orchestrates the workflow:
        1. Spawn silence detector thread to find silence boundaries
        2. Process silence pairs from queue as they arrive
        3. Build segments from detected silences
        4. Cut video segments (unless dry-run mode)
        5. Generate metadata for each segment
        6. Return list of Segment objects

        Args:
            input_file: Path to input video file.
            output_dir: Root output directory for namespace folders.
            namespace: Folder name and prefix for outputs (e.g., "video_1").
            noise: Silence detection threshold (default: "-10dB").
            silence_duration: Minimum silence duration to split on (default: 3.5s).
            padding: Padding around silence boundaries (default: 1.0s).
            threads: Number of worker threads for cutting (default: 2).
            min_segment: Minimum segment duration to keep (default: 3.0s).
            dry_run: If True, only detect silences without cutting (default: False).

        Returns:
            List of Segment objects representing split video parts.
        """
        # Print detection header
        print(f"Detecting silences (threshold={noise}, min gap={silence_duration}s)...\n")

        # Create component instances
        detector = SilenceDetector(
            input_file=input_file,
            noise=noise,
            duration=silence_duration,
            padding=padding
        )
        metadata_gen = MetadataGenerator(input_file=input_file)
        cutter = SegmentCutter(
            input_file=input_file,
            output_dir=output_dir,
            namespace=namespace,
            metadata_gen=metadata_gen,
            num_threads=threads,
            min_segment=min_segment
        )

        # Create queue for silence pairs (producer → consumer)
        q = queue.Queue()

        # Spawn detector thread
        detector_thread = detector.spawn_detector_thread(q)

        # Process silence pairs from queue
        segments = []  # List of (start, end) tuples
        prev_end = 0.0
        segment_id = 0

        while True:
            # Get next item from queue (silence pair or SENTINEL)
            item = q.get()

            # Check for SENTINEL (end of detection)
            if item is None:
                # Get video duration and add final segment
                duration = self._get_video_duration(input_file)

                # Add final segment if there's content after last silence
                if prev_end < duration:
                    segment_id += 1
                    segments.append((prev_end, duration))
                    print(
                        f"Segment {segment_id}: {prev_end:.2f}s → {duration:.2f}s "
                        f"({duration - prev_end:.1f}s)"
                    )

                break

            # Unpack silence boundaries
            cut_before, cut_after = item

            # Calculate segment length (from prev_end to cut_before)
            length = cut_before - prev_end

            # Check if segment meets minimum length requirement
            if length >= min_segment:
                segment_id += 1
                segments.append((prev_end, cut_before))
                print(
                    f"Segment {segment_id}: {prev_end:.2f}s → {cut_before:.2f}s "
                    f"({length:.1f}s)"
                )
            else:
                # Skip segment that's too short
                print(
                    f"Skipping {prev_end:.2f}s → {cut_before:.2f}s "
                    f"({length:.1f}s < {min_segment}s)"
                )

            # Move past this silence
            prev_end = cut_after

        # Wait for detector thread to finish
        detector_thread.join(timeout=30)

        # Cut segments if not in dry-run mode
        result_segments = []
        if not dry_run and segments:
            print()  # Blank line before cutting
            cutter.cut_segments(segments)

            # Build Segment objects from cut results
            for segment_id, (start, end) in enumerate(segments, start=1):
                segment_name = f"segment_{segment_id:03d}"
                filepath = f"{output_dir}/{namespace}/{segment_name}.mp4"
                metadata_path = f"{output_dir}/{namespace}/{segment_name}.yaml"

                result_segments.append(
                    Segment(
                        segment_id=segment_id,
                        start=start,
                        end=end,
                        filepath=filepath,
                        metadata_path=metadata_path
                    )
                )

            print(f"\nDone — {len(result_segments)} segments saved to {output_dir}/{namespace}/")
        elif segments:
            # Dry-run mode: create Segment objects without cutting
            for segment_id, (start, end) in enumerate(segments, start=1):
                segment_name = f"segment_{segment_id:03d}"
                filepath = f"{output_dir}/{namespace}/{segment_name}.mp4"
                metadata_path = f"{output_dir}/{namespace}/{segment_name}.yaml"

                result_segments.append(
                    Segment(
                        segment_id=segment_id,
                        start=start,
                        end=end,
                        filepath=filepath,
                        metadata_path=metadata_path
                    )
                )

            print(f"\nDone — {len(result_segments)} segments previewed (dry-run mode)")

        return result_segments

    @staticmethod
    def _get_video_duration(input_file: str) -> float:
        """
        Get video duration using ffprobe.

        Args:
            input_file: Path to video file.

        Returns:
            Duration in seconds as a float.

        Raises:
            RuntimeError: If ffprobe fails or duration cannot be parsed.
        """
        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-show_entries', 'format=duration',
                    '-of', 'json',
                    input_file
                ],
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            duration = float(data['format']['duration'])
            return duration
        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError) as e:
            raise RuntimeError(f"Failed to get video duration for {input_file}: {e}")
