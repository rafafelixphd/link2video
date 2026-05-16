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

        Raises:
            FileNotFoundError: If input_file does not exist
        """
        # Validate input file exists
        if not os.path.isfile(input_file):
            raise FileNotFoundError(f"Input file not found: {input_file}")

        self.input_file = input_file
        self.output_dir = output_dir
        self.namespace = namespace
        self.metadata_gen = metadata_gen
        self.num_threads = num_threads
        self.min_segment = min_segment

        # Create namespace directory path
        self.namespace_dir = os.path.join(output_dir, namespace)

        # Ensure output directory exists
        os.makedirs(self.namespace_dir, exist_ok=True)

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
        # Build output filename and metadata path
        segment_name = f"segment_{segment_id:03d}"
        output_path = os.path.join(self.namespace_dir, f"{segment_name}{self.file_extension}")
        metadata_path = os.path.join(self.namespace_dir, f"{segment_name}.yaml")

        # Build ffmpeg command with stream copy (no re-encoding)
        # NOTE: -y flag MUST come before output path for correct behavior
        ffmpeg_cmd = [
            'ffmpeg',
            '-i', self.input_file,
            '-ss', str(start),
            '-to', str(end),
            '-c', 'copy',
            '-avoid_negative_ts', 'make_zero',
            '-y',  # Overwrite output file without prompting
            output_path,
        ]

        try:
            # Run ffmpeg with suppressed output
            subprocess.run(
                ffmpeg_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True
            )

            # Write metadata file with error handling
            try:
                self.metadata_gen.write_metadata(
                    segment_id=segment_id,
                    original_file=self.input_file,
                    start=start,
                    end=end,
                    output_path=metadata_path,
                )
            except Exception as e:
                print(f"  ERROR: Segment {segment_id} metadata write failed: {e}", file=sys.stderr)
                return False

            return True
        except subprocess.CalledProcessError as e:
            print(f"  ERROR: Segment {segment_id} cutting failed: {e.stderr.decode() if e.stderr else str(e)}", file=sys.stderr)
            return False
        except Exception as e:
            print(f"  ERROR: Segment {segment_id} processing failed: {e}", file=sys.stderr)
            return False

    def _worker(self, job_queue: queue.Queue) -> None:
        """
        Worker thread that processes jobs from the queue.

        Each job is a tuple of (segment_id, start, end).
        Processes jobs until receiving None (sentinel).

        Args:
            job_queue: Queue containing jobs to process
        """
        try:
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
                    segments_cut = self.segments_cut
                    total = self.total_segments
                    status = '✓' if success else '✗'
                    segment_id_str = f"{segment_id:03d}"

                print(f"  [{segments_cut}/{total}] Cutting segment_{segment_id_str}.mp4... {status}")
        except Exception as e:
            print(f"  ERROR: Worker thread crashed: {e}", file=sys.stderr)

    def cut_segments(self, segments: list) -> int:
        """
        Cut all video segments using worker threads.

        Args:
            segments: List of (segment_id, start, end) tuples representing pre-numbered segment boundaries

        Returns:
            Number of successfully cut segments

        Raises:
            ValueError: If segments list is empty or contains invalid boundaries
        """
        # Validate segments list is not empty
        if not segments:
            print("WARNING: No segments to cut", file=sys.stderr)
            return 0

        # Validate segment boundaries (start < end)
        for i, (segment_id, start, end) in enumerate(segments):
            if start >= end:
                raise ValueError(f"Invalid segment {segment_id}: start ({start}) >= end ({end})")

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

        # Queue all jobs with pre-assigned segment IDs
        for segment_id, start, end in segments:
            job_queue.put((segment_id, start, end))

        # Send sentinel to each worker to signal completion
        for _ in range(self.num_threads):
            job_queue.put(None)

        # Wait for all workers to complete with timeout (600 seconds = 10 minutes)
        for worker in workers:
            worker.join(timeout=600)

        return self.segments_cut
