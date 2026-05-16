#!/usr/bin/env python3
"""
Split a video into segments by detecting silent gaps with ffmpeg.
Uses a producer/consumer pipeline — cutting starts as soon as the
first silence boundary is detected, not after the full scan finishes.

Usage:
    python silence_split.py input.mp4
    python silence_split.py input.mp4 -n -10dB -d 2 -m 3 -o segments
    python silence_split.py input.mp4 --dry-run
"""

import argparse
import subprocess
import re
import os
import sys
import threading
import queue


SENTINEL = None  # signals end of detection


def producer(input_file: str, noise: str, duration: float, q: queue.Queue):
    """
    Stream ffmpeg silencedetect stderr line by line.
    Each time a silence_end is found, push (silence_start, silence_end) to the queue.
    """
    cmd = [
        "ffmpeg", "-i", input_file,
        "-af", f"silencedetect=noise={noise}:d={duration}",
        "-f", "null", "-"
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
            q.put((pending_start, silence_end))
            pending_start = None

    proc.wait()
    q.put(SENTINEL)


def consumer(input_file: str, q: queue.Queue, output_dir: str, min_segment: float, dry_run: bool):
    """
    Read silence pairs from the queue. For each pair, figure out the
    non-silent segment that just ended and cut it immediately.
    """
    try:
        os.makedirs(output_dir, exist_ok=True)
    except Exception as e:
        print(f"Error: unable to create output directory {output_dir}: {e}", file=sys.stderr)
        return

    ext = os.path.splitext(input_file)[1] or ".mp4"

    prev_end = 0.0
    seg_num = 0
    successful_cuts = 0

    while True:
        item = q.get()

        if item is SENTINEL:
            # Final segment: from last silence end to end of file
            seg_num += 1
            if dry_run:
                print(f"  Segment {seg_num}: {prev_end:.2f}s → EOF")
            else:
                out_path = os.path.join(output_dir, f"segment_{seg_num:03d}{ext}")
                print(f"  [{seg_num}] {prev_end:.2f}s → EOF  →  {out_path}")
                if _cut(input_file, prev_end, None, out_path):
                    successful_cuts += 1
            break

        s_start, s_end = item
        seg_length = s_start - prev_end

        if s_start > prev_end and seg_length >= min_segment:
            seg_num += 1
            if dry_run:
                print(f"  Segment {seg_num}: {prev_end:.2f}s → {s_start:.2f}s ({seg_length:.1f}s)")
            else:
                out_path = os.path.join(output_dir, f"segment_{seg_num:03d}{ext}")
                print(f"  [{seg_num}] {prev_end:.2f}s → {s_start:.2f}s ({seg_length:.1f}s)  →  {out_path}")
                if _cut(input_file, prev_end, s_start, out_path):
                    successful_cuts += 1
        elif s_start > prev_end:
            print(f"  Skipping {prev_end:.2f}s → {s_start:.2f}s ({seg_length:.1f}s < {min_segment}s)")

        prev_end = s_end

    action = "previewed" if dry_run else "saved to"
    if not dry_run:
        print(f"\nDone — {successful_cuts}/{seg_num} segments {action} {output_dir}/")
    else:
        print(f"\nDone — {seg_num} segments {action} {output_dir}/")


def _cut(input_file: str, start: float, end: float | None, out_path: str) -> bool:
    """Run ffmpeg to extract one segment with stream copy.

    Returns:
        True if successful, False otherwise.
    """
    try:
        cmd = ["ffmpeg", "-i", input_file, "-ss", str(start)]
        if end is not None:
            cmd += ["-to", str(end)]
        cmd += ["-c", "copy", "-avoid_negative_ts", "make_zero", out_path, "-y"]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            print(f"Warning: ffmpeg failed for segment: {result.stderr}", file=sys.stderr)
            return False
        return True
    except subprocess.TimeoutExpired:
        print(f"Error: ffmpeg timeout while cutting segment to {out_path}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Error: unexpected error while cutting segment: {e}", file=sys.stderr)
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Split a video into segments at silent gaps using ffmpeg silencedetect. "
                    "Cutting starts as soon as silences are detected (pipeline mode)."
    )
    parser.add_argument("input", help="Input video file")
    parser.add_argument("-n", "--noise", default="-10dB",
                        help="Silence threshold in dB (default: -10dB)")
    parser.add_argument("-d", "--duration", type=float, default=2.0,
                        help="Minimum silence duration in seconds to count as a split point (default: 2.0)")
    parser.add_argument("-m", "--min-segment", type=float, default=3.0,
                        help="Minimum segment duration in seconds; shorter segments are discarded (default: 3.0)")
    parser.add_argument("-o", "--output-dir", default="segments",
                        help="Output directory for segments (default: segments)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only detect silences and show planned segments, don't cut")

    args = parser.parse_args()

    # Input validation
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    if args.duration <= 0:
        print(f"Error: duration must be positive, got {args.duration}", file=sys.stderr)
        sys.exit(1)

    if args.min_segment < 0:
        print(f"Error: min-segment must be non-negative, got {args.min_segment}", file=sys.stderr)
        sys.exit(1)

    print(f"Pipeline mode — detecting silence (threshold={args.noise}, min gap={args.duration}s)")
    print(f"Cutting segments as they're found (min length={args.min_segment}s)\n")

    q = queue.Queue()

    # Producer: streams ffmpeg output, pushes silence pairs to queue
    detector = threading.Thread(
        target=producer,
        args=(args.input, args.noise, args.duration, q),
        daemon=True
    )

    try:
        detector.start()
        # Consumer: reads queue, cuts segments as they arrive
        consumer(args.input, q, args.output_dir, args.min_segment, args.dry_run)
    finally:
        # Wait for detector thread with timeout (30 seconds)
        detector.join(timeout=30)


if __name__ == "__main__":
    main()