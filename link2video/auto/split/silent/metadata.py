"""Metadata generator for silence-split segments."""

import json
import subprocess
from pathlib import Path
from typing import Optional

import yaml


class MetadataGenerator:
    """Generates metadata for video segments including FPS and frame information."""

    def __init__(self, input_file: str):
        """Initialize MetadataGenerator.

        Args:
            input_file: Path to the input video file.
        """
        self.input_file = input_file
        self._fps: Optional[float] = None

    def get_fps(self) -> float:
        """Extract FPS from video using ffprobe.

        Extracts the frame rate from the video using ffprobe, parses the
        r_frame_rate field (which can be a ratio like "30000/1001"), and
        caches the result to avoid repeated calls.

        Returns:
            The frames per second as a float.

        Raises:
            RuntimeError: If FPS extraction fails.
        """
        if self._fps is not None:
            return self._fps

        try:
            result = subprocess.run(
                [
                    'ffprobe',
                    '-v', 'error',
                    '-select_streams', 'v:0',
                    '-show_entries', 'stream=r_frame_rate',
                    '-of', 'json',
                    self.input_file
                ],
                capture_output=True,
                text=True,
                check=True
            )

            data = json.loads(result.stdout)
            frame_rate_str = data['streams'][0]['r_frame_rate']

            # Parse frame rate ratio (e.g., "30000/1001" or "30/1")
            if '/' in frame_rate_str:
                numerator, denominator = frame_rate_str.split('/')
                self._fps = float(numerator) / float(denominator)
            else:
                self._fps = float(frame_rate_str)

            return self._fps

        except (subprocess.CalledProcessError, json.JSONDecodeError, KeyError, ValueError) as e:
            raise RuntimeError(f"Failed to extract FPS from {self.input_file}: {e}")

    def frame_from_timestamp(self, timestamp: float) -> int:
        """Calculate frame number from timestamp.

        Args:
            timestamp: Time in seconds.

        Returns:
            The frame number (0-indexed).
        """
        fps = self.get_fps()
        return int(timestamp * fps)

    def write_metadata(
        self,
        segment_id: int,
        original_file: str,
        start: float,
        end: float,
        output_path: str
    ) -> None:
        """Write metadata YAML file for a segment.

        Creates a YAML file with segment metadata including frame numbers
        and timestamps. Creates parent directory if needed.

        Args:
            segment_id: Segment identifier (will be padded to 3 digits).
            original_file: Path to the original input video file.
            start: Start time in seconds.
            end: End time in seconds.
            output_path: Path where the YAML file should be written.
        """
        # Create parent directory if it doesn't exist
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        # Get FPS and calculate frame numbers
        fps = self.get_fps()
        start_frame = self.frame_from_timestamp(start)
        end_frame = self.frame_from_timestamp(end)

        # Create metadata dictionary with rounded values
        metadata = {
            'name': f'segment_{segment_id:03d}',
            'original_file': original_file,
            'fps': round(fps, 2),
            'start': round(start, 2),
            'end': round(end, 2),
            'start_frame': start_frame,
            'end_frame': end_frame,
        }

        # Write YAML file
        with open(output_path, 'w') as f:
            yaml.dump(metadata, f, default_flow_style=False, sort_keys=False)
