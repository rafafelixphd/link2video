"""
Job queue and process manager for batch segment processing.

Handles:
- Job persistence (JSON files in app/.jobs/)
- Job queueing and concurrency limiting
- Process spawning and monitoring
- PID tracking and cleanup
"""
import os
import json
import time
import uuid
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class JobManager:
    """Manages job queue, persistence, and process execution."""

    def __init__(self, jobs_dir: str = "app/.jobs"):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self.running_pids: Dict[str, int] = {}  # job_id -> pid

    def create_job(
        self,
        files: List[Dict[str, Any]],
        global_params: Dict[str, Any],
    ) -> str:
        """
        Create a new batch job and persist to disk.

        Args:
            files: List of file dicts with input, namespace, output_dir, parameters
            global_params: Global settings (job_concurrency, dry_run)

        Returns:
            job_id: Unique identifier for the job
        """
        job_id = self._generate_job_id()
        job_data = {
            "id": job_id,
            "tab": "segment",
            "created_at": datetime.utcnow().isoformat() + "Z",
            "started_at": None,
            "completed_at": None,
            "status": "pending",
            "pid": None,
            "files": [
                {
                    "input": f["input"],
                    "namespace": f["namespace"],
                    "output_dir": f["output_dir"],
                    "parameters": f["parameters"],
                    "status": "pending",
                    "progress": 0,
                    "segments_created": 0,
                    "error": None,
                    "stdout": "",
                    "stderr": "",
                }
                for f in files
            ],
            "global_parameters": global_params,
        }
        self._persist_job(job_id, job_data)
        return job_id

    def list_jobs(self) -> List[Dict[str, Any]]:
        """Return list of all jobs (running + completed)."""
        jobs = []
        for job_file in sorted(self.jobs_dir.glob("*.json")):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                    jobs.append({
                        "id": job["id"],
                        "status": job["status"],
                        "created_at": job["created_at"],
                        "files_count": len(job["files"]),
                        "completed_count": sum(1 for f in job["files"] if f["status"] == "completed"),
                        "failed_count": sum(1 for f in job["files"] if f["status"] == "failed"),
                    })
            except (json.JSONDecodeError, KeyError):
                pass
        return jobs

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load and return full job details."""
        job_file = self.jobs_dir / f"{job_id}.json"
        if not job_file.exists():
            return None
        try:
            with open(job_file) as f:
                return json.load(f)
        except json.JSONDecodeError:
            return None

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a running job by terminating its process."""
        job = self.get_job(job_id)
        if not job or not job.get("pid"):
            return False

        try:
            os.kill(job["pid"], 9)  # SIGKILL
            job["status"] = "cancelled"
            job["completed_at"] = datetime.utcnow().isoformat() + "Z"
            for f in job["files"]:
                if f["status"] == "running":
                    f["status"] = "cancelled"
            self._persist_job(job_id, job)
            return True
        except ProcessLookupError:
            return False

    def _generate_job_id(self) -> str:
        """Generate unique job ID based on timestamp."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique = str(uuid.uuid4())[:8]
        return f"{timestamp}_{unique}"

    def _persist_job(self, job_id: str, job_data: Dict[str, Any]) -> None:
        """Write job to JSON file."""
        job_file = self.jobs_dir / f"{job_id}.json"
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=2)

    def process_queue(self, job_concurrency: int = 2) -> None:
        """
        Process job queue: spawn next pending job if slots available.

        Called periodically by Flask to manage background jobs.
        """
        # Count currently running jobs
        running_count = 0
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                    if job["status"] == "running" and job.get("pid"):
                        # Check if process still alive
                        try:
                            os.kill(job["pid"], 0)  # Signal 0: check existence
                        except ProcessLookupError:
                            # Process dead; mark job as failed
                            job["status"] = "failed"
                            job["completed_at"] = datetime.utcnow().isoformat() + "Z"
                            self._persist_job(job["id"], job)
                            running_count -= 1
                            continue
                        running_count += 1
            except (json.JSONDecodeError, KeyError):
                pass

        # If slots available, spawn next pending file
        if running_count < job_concurrency:
            for job_file in self.jobs_dir.glob("*.json"):
                try:
                    with open(job_file) as f:
                        job = json.load(f)
                    if job["status"] != "pending":
                        continue

                    # Find first pending file in this job
                    for file_info in job["files"]:
                        if file_info["status"] == "pending":
                            self._spawn_segment_process(job, file_info)
                            job["status"] = "running"
                            job["started_at"] = datetime.utcnow().isoformat() + "Z"
                            self._persist_job(job["id"], job)
                            return  # Only spawn one at a time
                except (json.JSONDecodeError, KeyError):
                    pass

    def _spawn_segment_process(self, job: Dict[str, Any], file_info: Dict[str, Any]) -> None:
        """
        Spawn a background process to segment a single file.

        Imports SilenceSplitter directly and calls its split() method.
        """
        from link2video.auto.split.silent import SilenceSplitter

        file_info["status"] = "running"
        file_info["stdout"] = ""
        file_info["stderr"] = ""

        # Validate input file exists
        if not os.path.isfile(file_info["input"]):
            file_info["status"] = "failed"
            file_info["error"] = f"File not found: {file_info['input']}"
            self._persist_job(job["id"], job)
            return

        # Validate output directory
        output_path = Path(file_info["output_dir"])
        if not output_path.exists():
            try:
                output_path.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                file_info["status"] = "failed"
                file_info["error"] = f"Cannot create output dir: {str(e)}"
                self._persist_job(job["id"], job)
                return

        try:
            splitter = SilenceSplitter()
            segments = splitter.split(
                input_file=file_info["input"],
                output_dir=file_info["output_dir"],
                namespace=file_info["namespace"],
                threshold=file_info["parameters"]["threshold"],
                quiet_for=file_info["parameters"]["quiet_for"],
                padding=file_info["parameters"]["padding"],
                threads=file_info["parameters"]["threads"],
                skip_shorter=file_info["parameters"]["skip_shorter"],
                dry_run=job["global_parameters"].get("dry_run", False),
            )

            file_info["status"] = "completed"
            file_info["segments_created"] = len(segments) if segments else 0
            file_info["progress"] = 1.0

        except Exception as e:
            file_info["status"] = "failed"
            file_info["error"] = str(e)
            file_info["stderr"] = str(e)

        self._persist_job(job["id"], job)
