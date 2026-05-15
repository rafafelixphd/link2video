import os
import queue
import re
import subprocess
import sys
import threading
from typing import Optional, Tuple

SENTINEL = None


class SilenceDetector:
    """Detects silence in audio using ffmpeg silencedetect filter."""

    def __init__(
        self,
        input_file: str,
        noise: str = "-10dB",
        duration: float = 3.5,
        padding: float = 1.0
    ):
        """
        Initialize the SilenceDetector.

        Args:
            input_file: Path to the input audio/video file.
            noise: Silence detection threshold (default "-10dB").
            duration: Minimum silence duration in seconds (default 3.5).
            padding: Padding to apply around silences in seconds (default 1.0).

        Raises:
            FileNotFoundError: If input_file does not exist.
            ValueError: If duration <= 0 or padding < 0.
        """
        # Validate input_file exists
        if not os.path.isfile(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        # Validate duration is positive
        if duration <= 0:
            raise ValueError(f"duration must be positive, got {duration}")

        # Validate padding is non-negative
        if padding < 0:
            raise ValueError(f"padding must be non-negative, got {padding}")

        self.input_file = input_file
        self.noise = noise
        self.duration = duration
        self.padding = padding

    def detect(self, q: queue.Queue) -> None:
        """
        Run ffmpeg silencedetect filter and push cut points to queue.

        Parses silence_start and silence_end from ffmpeg stderr,
        applies padding, and pushes (cut_before, cut_after) tuples.
        Pushes SENTINEL when done.

        Args:
            q: Queue to push results to.
        """
        # Build ffmpeg command with silencedetect filter
        cmd = [
            "ffmpeg",
            "-i", self.input_file,
            "-af", f"silencedetect=n={self.noise}:d={self.duration}",
            "-f", "null",
            "-"
        ]

        process = None
        try:
            # Start ffmpeg process
            process = subprocess.Popen(
                cmd,
                stderr=subprocess.PIPE,
                stdout=subprocess.PIPE,
                text=False
            )

            # Regex patterns for parsing silence_start and silence_end
            silence_start_pattern = re.compile(rb"silence_start:\s*([\d.]+)")
            silence_end_pattern = re.compile(rb"silence_end:\s*([\d.]+)")

            current_silence_start: Optional[float] = None

            # Parse ffmpeg stderr line by line
            for line in process.stderr:
                # Try to match silence_start
                start_match = silence_start_pattern.search(line)
                if start_match:
                    current_silence_start = float(start_match.group(1))
                    continue

                # Try to match silence_end
                end_match = silence_end_pattern.search(line)
                if end_match and current_silence_start is not None:
                    try:
                        silence_end = float(end_match.group(1))

                        # Apply padding
                        cut_before = current_silence_start + self.padding
                        cut_after = silence_end - self.padding

                        # Check for inverted intervals and skip if necessary
                        if cut_before >= cut_after:
                            print(
                                f"Warning: inverted interval ({cut_before:.2f} >= {cut_after:.2f}), skipping",
                                file=sys.stderr
                            )
                        else:
                            # Push the cut point pair
                            q.put((cut_before, cut_after))

                        current_silence_start = None
                    except ValueError as e:
                        print(f"Error parsing silence values: {e}", file=sys.stderr)

        except FileNotFoundError:
            print("Error: ffmpeg not found. Please install ffmpeg.", file=sys.stderr)
        except Exception as e:
            print(f"Error during silence detection: {e}", file=sys.stderr)
        finally:
            # Ensure process is properly cleaned up
            if process is not None:
                try:
                    # Wait with timeout; terminate if it hangs
                    process.wait(timeout=60)
                except subprocess.TimeoutExpired:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                except Exception:
                    pass

            # Always push SENTINEL to signal completion
            q.put(SENTINEL)

    def spawn_detector_thread(self, q: queue.Queue) -> threading.Thread:
        """
        Start the detector in a daemon thread.

        Args:
            q: Queue to push results to.

        Returns:
            The started thread object.
        """
        thread = threading.Thread(target=self.detect, args=(q,), daemon=True)
        thread.start()
        return thread
