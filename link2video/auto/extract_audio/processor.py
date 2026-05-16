import os
import subprocess
from pathlib import Path
from typing import NamedTuple

import librosa
import numpy as np
import yaml


class AudioExtraction(NamedTuple):
    """Result of audio extraction."""
    audio_path: str
    metadata_path: str
    duration: float


class ExtractAudioProcessor:
    """Extracts audio from video/audio files with metadata generation."""

    def extract(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        format: str = "wav",
        dry_run: bool = False,
    ) -> AudioExtraction:
        """
        Extract audio from input file and generate metadata.

        Args:
            input_file: Path to video or audio file
            output_dir: Root output directory
            namespace: Output filename prefix
            format: Output format (wav or mp3)
            dry_run: Preview mode without writing files

        Returns:
            AudioExtraction with paths to audio and metadata files

        Raises:
            FileNotFoundError: If input file doesn't exist
            ValueError: If format is invalid
            RuntimeError: If FFmpeg or librosa operations fail
        """
        if not os.path.isfile(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        if format not in ("wav", "mp3"):
            raise ValueError(f"Invalid format: {format}. Must be 'wav' or 'mp3'")

        # Create output directory structure
        namespace_dir = os.path.join(output_dir, namespace)
        if not dry_run:
            os.makedirs(namespace_dir, exist_ok=True)

        audio_filename = f"{namespace}.{format}"
        audio_path = os.path.join(namespace_dir, audio_filename)
        metadata_path = os.path.join(namespace_dir, f"{namespace}.yaml")

        if dry_run:
            print(f"[DRY-RUN] Would extract audio to: {audio_path}")
            print(f"[DRY-RUN] Would save metadata to: {metadata_path}")
            return AudioExtraction(audio_path, metadata_path, 0.0)

        # Extract audio with FFmpeg
        print(f"Extracting audio from {input_file}...")

        quality_args = ["-q:a", "9"] if format == "mp3" else []

        ffmpeg_cmd = [
            "ffmpeg",
            "-i", input_file,
            *quality_args,
            "-n",
            audio_path,
        ]

        try:
            subprocess.run(ffmpeg_cmd, check=True, capture_output=True)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(f"FFmpeg extraction failed: {e.stderr.decode()}")
        except FileNotFoundError:
            raise RuntimeError("FFmpeg not found. Please install FFmpeg.")

        print(f"Audio extracted to: {audio_path}")

        # Get audio duration and metadata
        duration = self._get_duration(audio_path)

        # Generate audio level metadata
        print(f"Analyzing audio levels...")
        metadata = self._analyze_audio_levels(audio_path, duration)

        # Save metadata
        with open(metadata_path, "w") as f:
            yaml.dump(metadata, f, default_flow_style=False)

        print(f"Metadata saved to: {metadata_path}")

        return AudioExtraction(audio_path, metadata_path, duration)

    def _get_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds using ffprobe."""
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ]
        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            return float(result.stdout.strip())
        except (subprocess.CalledProcessError, ValueError) as e:
            raise RuntimeError(f"Failed to get duration: {e}")

    def _analyze_audio_levels(self, audio_path: str, duration: float) -> dict:
        """Analyze audio levels using librosa and return metadata dict."""
        try:
            y, sr = librosa.load(audio_path, sr=None)
        except Exception as e:
            raise RuntimeError(f"Failed to load audio with librosa: {e}")

        # Compute mel spectrogram and convert to dB
        S = librosa.feature.melspectrogram(y=y, sr=sr)
        S_db = librosa.power_to_db(S, ref=np.max)

        # Extract energy per frame (mean across frequency bins)
        energy = np.mean(S_db, axis=0)

        return {
            "audio": {
                "format": audio_path.split(".")[-1],
                "duration": float(duration),
                "sample_rate": int(sr),
                "channels": 1 if y.ndim == 1 else y.shape[0],
            },
            "audio_levels": {
                "min_db": float(np.min(energy)),
                "max_db": float(np.max(energy)),
                "mean_db": float(np.mean(energy)),
                "peak_db": float(np.percentile(energy, 99)),
                "db_array": energy.tolist(),
            },
        }
