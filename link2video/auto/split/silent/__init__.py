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
        threshold: str = "-10dB",
        quiet_for: float = 3.5,
        padding: float = 1.0,
        threads: int = 2,
        skip_shorter: float = 3.0,
        dry_run: bool = False
    ) -> List[Segment]:

        # Store padding for diagnostic output
        self._padding = padding
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
            threshold: Silence detection threshold (default: "-10dB").
            quiet_for: Minimum silence duration to split on (default: 3.5s).
            padding: Padding around silence boundaries (default: 1.0s).
            threads: Number of worker threads for cutting (default: 2).
            skip_shorter: Minimum segment duration to keep (default: 3.0s).
            dry_run: If True, only detect silences without cutting (default: False).

        Returns:
            List of Segment objects representing split video parts.
        """
        # Print detection header
        print(f"Detecting silences (threshold={threshold}, min gap={quiet_for}s)...\n")

        # Create component instances
        detector = SilenceDetector(
            input_file=input_file,
            threshold=threshold,
            duration=quiet_for,
            padding=padding
        )
        metadata_gen = MetadataGenerator(input_file=input_file)
        cutter = SegmentCutter(
            input_file=input_file,
            output_dir=output_dir,
            namespace=namespace,
            metadata_gen=metadata_gen,
            num_threads=threads,
            skip_shorter=skip_shorter
        )

        # Create queue for silence pairs (producer → consumer)
        q = queue.Queue()

        # Spawn detector thread
        detector_thread = detector.spawn_detector_thread(q)

        # Collect all silence pairs from queue (sliding window uses them all at once)
        silences = []
        while True:
            item = q.get()
            if item is None:
                break
            silences.append(item)

        # Get video duration for final segment handling
        duration = self._get_video_duration(input_file)

        # Sliding window: process segments between silences
        # Store: (segment_id, save_start, save_end) for cutter
        # Also track audio boundaries for diagnostics
        segments = []
        segment_info = []  # For diagnostic output
        segment_id = 0
        current_pos = 0.0

        for silence_start, silence_end in silences:
            # Segment: from current position to where silence starts
            audio_start = current_pos
            audio_end = silence_start
            audio_duration = audio_end - audio_start

            # Check if segment meets minimum length requirement
            if audio_duration >= skip_shorter:
                segment_id += 1

                # Calculate save boundaries with padding
                save_start = max(audio_start - padding, 0.0)
                save_end = min(audio_end + padding, duration)
                save_duration = save_end - save_start

                # Store for cutter (with padding applied)
                segments.append((segment_id, save_start, save_end))
                segment_info.append({
                    'id': segment_id,
                    'audio_start': audio_start,
                    'audio_end': audio_end,
                    'audio_duration': audio_duration,
                    'save_start': save_start,
                    'save_end': save_end,
                    'save_duration': save_duration,
                    'padding': padding
                })

                segment_name = f"segment_{segment_id:03d}"
                print(
                    f"[AUDIO] {segment_name}: Start at: {audio_start:.2f}s - End at: {audio_end:.2f}s ({audio_duration:.2f}s audio)"
                )
                print(
                    f"  Saving with padding ({padding:.1f}s): {save_start:.2f}s to {save_end:.2f}s ({save_duration:.2f}s total) - saving to: {segment_name}.mp4"
                )
            else:
                # Skip segment that's too short
                print(
                    f"[AUDIO] Skipping: Start at: {audio_start:.2f}s - End at: {audio_end:.2f}s "
                    f"({audio_duration:.2f}s < {skip_shorter}s minimum)"
                )

            # Print the silence period (not saved)
            print(
                f"[SILENCE] Start at: {silence_start:.2f}s - End at: {silence_end:.2f}s ({silence_end - silence_start:.2f}s) - REMOVED (not saved)"
            )

            # Move past this silence
            current_pos = silence_end

        # Handle final segment (after last silence)
        if current_pos < duration:
            audio_start = current_pos
            audio_end = duration
            audio_duration = audio_end - audio_start

            if audio_duration >= skip_shorter:
                segment_id += 1

                # Calculate save boundaries with padding (no padding after final end)
                save_start = max(audio_start - padding, 0.0)
                save_end = duration
                save_duration = save_end - save_start

                # Store for cutter (with padding applied)
                segments.append((segment_id, save_start, save_end))
                segment_info.append({
                    'id': segment_id,
                    'audio_start': audio_start,
                    'audio_end': audio_end,
                    'audio_duration': audio_duration,
                    'save_start': save_start,
                    'save_end': save_end,
                    'save_duration': save_duration,
                    'padding': padding
                })

                segment_name = f"segment_{segment_id:03d}"
                print(
                    f"[AUDIO] {segment_name}: Start at: {audio_start:.2f}s - End at: {audio_end:.2f}s ({audio_duration:.2f}s audio)"
                )
                print(
                    f"  Saving with padding ({padding:.1f}s): {save_start:.2f}s to {save_end:.2f}s ({save_duration:.2f}s total) - saving to: {segment_name}.mp4"
                )
            else:
                print(
                    f"[AUDIO] Skipping: Start at: {audio_start:.2f}s - End at: {audio_end:.2f}s "
                    f"({audio_duration:.2f}s < {skip_shorter}s minimum)"
                )

        # Wait for detector thread to finish
        detector_thread.join(timeout=30)

        # Cut segments if not in dry-run mode
        result_segments = []
        if not dry_run and segments:
            print()  # Blank line before cutting
            cutter.cut_segments(segments)

            # Build Segment objects from cut results
            for segment_id, start, end in segments:
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
            for segment_id, start, end in segments:
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
