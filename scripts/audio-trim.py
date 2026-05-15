#!/usr/bin/env python3
"""
Video splitter that detects silence and splits videos into multiple files.
"""

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import librosa
import numpy as np


def extract_audio(video_path: str, temp_dir: str) -> str:
    """Extract audio from video and return path to wav file."""
    audio_path = os.path.join(temp_dir, "audio.wav")
    cmd = [
        "ffmpeg",
        "-i", video_path,
        "-q:a", "9",
        "-n",
        audio_path,
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return audio_path


def detect_silence(audio_path: str, silence_duration: float, threshold_db: float = -40) -> list:
    """
    Detect silence segments in audio.

    Returns list of (start_time, end_time) tuples for silence.
    """
    y, sr = librosa.load(audio_path, sr=None)
    S = librosa.feature.melspectrogram(y=y, sr=sr)
    S_db = librosa.power_to_db(S, ref=np.max)
    energy = np.mean(S_db, axis=0)

    silence_threshold = threshold_db
    is_silent = energy < silence_threshold

    frames = np.arange(len(is_silent))
    time_frames = librosa.frames_to_time(frames, sr=sr)

    silence_segments = []
    in_silence = False
    silence_start = 0

    for i, (t, silent) in enumerate(zip(time_frames, is_silent)):
        if silent and not in_silence:
            silence_start = t
            in_silence = True
        elif not silent and in_silence:
            silence_end = t
            if silence_end - silence_start >= silence_duration:
                silence_segments.append((silence_start, silence_end))
            in_silence = False

    return silence_segments


def get_video_duration(video_path: str) -> float:
    """Get duration of video in seconds."""
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1:nokey=1",
        video_path,
    ]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    return float(result.stdout.strip())


def split_video(
    video_path: str,
    silence_segments: list,
    namespace: str,
    output_dir: str = "."
) -> None:
    """
    Split video at silence points and save segments.
    """
    video_ext = Path(video_path).suffix[1:]
    total_duration = get_video_duration(video_path)

    split_points = [0]
    for start, end in silence_segments:
        split_points.append(start)
        split_points.append(end)
    split_points.append(total_duration)

    split_points = sorted(set(split_points))

    segment_id = 1
    for i in range(0, len(split_points) - 1, 2):
        start = split_points[i]
        end = split_points[i + 1] if i + 1 < len(split_points) else total_duration

        if end - start < 0.1:
            continue

        output_file = os.path.join(output_dir, f"{namespace}_{segment_id:03d}.{video_ext}")

        cmd = [
            "ffmpeg",
            "-i", video_path,
            "-ss", str(start),
            "-to", str(end),
            "-c", "copy",
            "-n",
            output_file,
        ]

        print(f"Extracting segment {segment_id}: {start:.2f}s - {end:.2f}s -> {output_file}")
        subprocess.run(cmd, check=True, capture_output=True)
        segment_id += 1


def main():
    parser = argparse.ArgumentParser(
        description="Split video by silence segments"
    )
    parser.add_argument("video", help="Path to video file")
    parser.add_argument(
        "silence_duration",
        type=float,
        help="Minimum silence duration in seconds to trigger a split",
    )
    parser.add_argument(
        "namespace",
        help="Namespace for output files (format: {namespace}_{id}.{ext})",
    )
    parser.add_argument(
        "-o", "--output-dir",
        default=".",
        help="Output directory (default: current directory)",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=-40,
        help="Audio level threshold in dB for silence detection (default: -40)",
    )

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"Error: Video file not found: {args.video}")
        return 1

    os.makedirs(args.output_dir, exist_ok=True)

    with tempfile.TemporaryDirectory() as temp_dir:
        print(f"Extracting audio from {args.video}...")
        audio_path = extract_audio(args.video, temp_dir)

        print(f"Detecting silence (threshold: {args.threshold}dB, min duration: {args.silence_duration}s)...")
        silence_segments = detect_silence(
            audio_path,
            args.silence_duration,
            args.threshold
        )

        if not silence_segments:
            print("No silence segments detected. Video will not be split.")
            return 0

        print(f"Found {len(silence_segments)} silence segment(s)")
        for start, end in silence_segments:
            print(f"  {start:.2f}s - {end:.2f}s")

        print(f"\nSplitting video...")
        split_video(args.video, silence_segments, args.namespace, args.output_dir)

    print("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
