import subprocess
import os
import threading
import queue
import sys
from .metadata import MetadataGenerator


class SegmentCutter:
    """
    Multi-threaded video segment cutter using stream copy (no re-encoding).

    Uses a worker thread pool to cut video segments in parallel with real-time
    progress display.
    """

    def __init__(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        metadata_gen: 'MetadataGenerator',
        num_threads: int = 2,
        min_segment: float = 3.0
    ):
        """
        Initialize the SegmentCutter.

        Args:
            input_file: Path to the input video file
            output_dir: Output directory for segments
            namespace: Namespace/folder name for segments
            metadata_gen: MetadataGenerator instance for writing metadata
            num_threads: Number of worker threads (default: 2)
            min_segment: Minimum segment duration in seconds (default: 3.0)
        """
        self.input_file = input_file
        self.output_dir = output_dir
        self.namespace = namespace
        self.metadata_gen = metadata_gen
        self.num_threads = num_threads
        self.min_segment = min_segment

        # Create namespace directory path
        self.namespace_dir = os.path.join(output_dir, namespace)

        # Get file extension from input file
        self.file_extension = os.path.splitext(input_file)[1] or '.mp4'

        # Thread-safe progress tracking
        self.lock = threading.Lock()
        self.segments_cut = 0
        self.total_segments = 0

    def _cut_segment(self, segment_id: int, start: float, end: float) -> bool:
        """
        Cut a single video segment using ffmpeg stream copy.

        Args:
            segment_id: Segment identifier (1-indexed)
            start: Start time in seconds
            end: End time in seconds

        Returns:
            True if successful, False otherwise
        """
        # Create namespace directory if needed
        os.makedirs(self.namespace_dir, exist_ok=True)

        # Build output filename and metadata path
        segment_name = f"segment_{segment_id:03d}"
        output_path = os.path.join(self.namespace_dir, f"{segment_name}{self.file_extension}")
        metadata_path = os.path.join(self.namespace_dir, f"{segment_name}.yaml")

        # Build ffmpeg command with stream copy (no re-encoding)
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', self.input_file,
            '-ss', str(start),
            '-to', str(end),
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            output_path,
            '-y'
        ]

        try:
            # Run ffmpeg with suppressed output
            result = subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            # Call metadata generator to write metadata
            self.metadata_gen.write_metadata(
                segment_id=segment_id,
                original_file=self.input_file,
                start=start,
                end=end,
                output_path=metadata_path,
            )

            return True
        except subprocess.CalledProcessError as e:
            return False
        except Exception as e:
            return False

    def _worker(self, job_queue: queue.Queue) -> None:
        """
        Worker thread that processes jobs from the queue.

        Each job is a tuple of (segment_id, start, end).
        Processes jobs until receiving None (sentinel).

        Args:
            job_queue: Queue containing jobs to process
        """
        while True:
            job = job_queue.get()

            # Check for sentinel value
            if job is None:
                break

            segment_id, start, end = job

            # Cut the segment
            success = self._cut_segment(segment_id, start, end)

            # Update progress with thread-safe lock
            with self.lock:
                self.segments_cut += 1
                status = '✓' if success else '✗'
                print(f"  [{self.segments_cut}/{self.total_segments}] Cutting segment_{segment_id:03d}.mp4... {status}")

    def cut_segments(self, segments: list) -> None:
        """
        Cut all video segments using worker threads.

        Args:
            segments: List of (start, end) tuples representing segment boundaries
        """
        # Set total segments count
        self.total_segments = len(segments)
        self.segments_cut = 0

        # Print header
        print(f"Cutting segments ({self.num_threads} workers):")

        # Create job queue
        job_queue = queue.Queue()

        # Spawn worker threads
        workers = []
        for _ in range(self.num_threads):
            worker = threading.Thread(
                target=self._worker,
                args=(job_queue,),
                daemon=True
            )
            worker.start()
            workers.append(worker)

        # Queue all jobs with segment numbering starting from 1
        for segment_id, (start, end) in enumerate(segments, start=1):
            job_queue.put((segment_id, start, end))

        # Send sentinel to each worker to signal completion
        for _ in range(self.num_threads):
            job_queue.put(None)

        # Wait for all workers to complete
        for worker in workers:
            worker.join()
