"""
Job queue and process manager for batch segment processing.

Handles:
- Job persistence (JSON files in app/.jobs/)
- Job queueing and concurrency limiting
- Subprocess spawning and PID tracking
- Async process monitoring
"""
import os
import json
import subprocess
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


class JobManager:
    """Manages job queue, persistence, and subprocess execution."""

    def __init__(self, jobs_dir: str = "app/.jobs"):
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)

    def create_job(
        self,
        files: List[Dict[str, Any]],
        global_params: Dict[str, Any],
    ) -> str:
        """Create a new batch job and persist to disk."""
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
        for job_file in sorted(self.jobs_dir.glob("*.json"), reverse=True):
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
        """Cancel a running job by terminating its process and deleting the job."""
        job = self.get_job(job_id)
        if not job:
            return False

        # Kill process if running
        if job.get("pid"):
            try:
                os.kill(job["pid"], 9)  # SIGKILL
            except ProcessLookupError:
                pass

        # Delete job file and associated files
        self._delete_job(job_id)
        return True

    def delete_job(self, job_id: str) -> bool:
        """Delete a job and all associated files."""
        self._delete_job(job_id)
        return True

    def _delete_job(self, job_id: str) -> None:
        """Remove job JSON and all associated files."""
        # Delete job JSON
        job_file = self.jobs_dir / f"{job_id}.json"
        if job_file.exists():
            job_file.unlink()

        # Delete subprocess log
        log_file = self.jobs_dir / f"{job_id}_subprocess.log"
        if log_file.exists():
            log_file.unlink()

        # Delete config file
        config_file = self.jobs_dir / f"{job_id}_config.json"
        if config_file.exists():
            config_file.unlink()

    def clear_all_jobs(self) -> None:
        """Delete all job files and associated data."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                job_id = job_file.stem
                self._delete_job(job_id)
            except Exception:
                pass

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

    def process_queue(self) -> None:
        """
        Process job queue: monitor running processes and spawn new ones.

        Called on each Flask request to:
        1. Check if running processes are still alive
        2. Mark completed/failed jobs
        3. Spawn next pending file if slots available
        """
        # First, update status of all running processes
        self._monitor_running_processes()

        # Recalculate status for all jobs based on file states
        self._update_all_job_statuses()

        # Then spawn new processes if slots available
        self._spawn_pending_files()

    def _monitor_running_processes(self) -> None:
        """Check status of all running processes and update job state."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)

                if job["status"] not in ["pending", "running"]:
                    continue

                if not job.get("pid"):
                    continue

                # Check if process still alive
                try:
                    os.kill(job["pid"], 0)  # Signal 0 = check existence
                    # Still running
                except ProcessLookupError:
                    # Process died; find which file was being processed
                    for f in job["files"]:
                        if f["status"] == "running":
                            f["status"] = "completed"
                            f["progress"] = 1.0
                            job["pid"] = None
                            self._persist_job(job["id"], job)
                            break

                    # Update job status based on all files
                    self._update_job_status(job)
                    self._persist_job(job["id"], job)

            except (json.JSONDecodeError, KeyError):
                pass

    def _update_job_status(self, job: Dict[str, Any]) -> None:
        """Update job status based on all file statuses."""
        statuses = [f["status"] for f in job["files"]]

        if all(s == "completed" for s in statuses):
            job["status"] = "completed"
            job["completed_at"] = datetime.utcnow().isoformat() + "Z"
        elif all(s in ["failed", "cancelled"] for s in statuses):
            job["status"] = "failed"
            job["completed_at"] = datetime.utcnow().isoformat() + "Z"
        elif any(s == "running" for s in statuses):
            job["status"] = "running"
        elif any(s == "pending" for s in statuses):
            job["status"] = "pending"

    def _update_all_job_statuses(self) -> None:
        """Recalculate status for all jobs based on their file states."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)

                if job["status"] in ["completed", "failed", "cancelled"]:
                    continue

                self._update_job_status(job)
                self._persist_job(job["id"], job)
            except (json.JSONDecodeError, KeyError):
                pass

    def _spawn_pending_files(self) -> None:
        """Spawn background processes for pending files."""
        # Count currently running processes
        running_count = sum(
            1 for job_file in self.jobs_dir.glob("*.json")
            if self._job_has_running_pid(job_file)
        )

        # Get concurrency limit from first running/pending job
        job_concurrency = 2
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                if job["status"] in ["pending", "running"]:
                    job_concurrency = min(
                        job["global_parameters"].get("job_concurrency", 2),
                        8
                    )
                    break
            except (json.JSONDecodeError, KeyError):
                pass

        # Spawn next pending file if slots available
        if running_count < job_concurrency:
            for job_file in sorted(self.jobs_dir.glob("*.json")):
                try:
                    with open(job_file) as f:
                        job = json.load(f)

                    if job["status"] not in ["pending", "running"]:
                        continue

                    # Find first pending file
                    for file_info in job["files"]:
                        if file_info["status"] == "pending":
                            self._spawn_subprocess(job, file_info)
                            self._update_job_status(job)
                            self._persist_job(job["id"], job)
                            return  # Only spawn one at a time

                except (json.JSONDecodeError, KeyError):
                    pass

    def _job_has_running_pid(self, job_file: Path) -> bool:
        """Check if job file has a running process."""
        try:
            with open(job_file) as f:
                job = json.load(f)
            if not job.get("pid"):
                return False
            try:
                os.kill(job["pid"], 0)
                return True
            except ProcessLookupError:
                return False
        except (json.JSONDecodeError, KeyError):
            return False

    def _spawn_subprocess(self, job: Dict[str, Any], file_info: Dict[str, Any]) -> None:
        """Spawn a background subprocess for a single file."""
        input_file = file_info["input"]
        namespace = file_info["namespace"]
        output_dir = file_info["output_dir"]
        params = file_info["parameters"]

        # Validate input file
        if not os.path.isfile(input_file):
            file_info["status"] = "failed"
            file_info["error"] = f"File not found: {input_file}"
            return

        # Create output directory
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except Exception as e:
            file_info["status"] = "failed"
            file_info["error"] = f"Cannot create output dir: {str(e)}"
            return

        # Create config file for worker script
        config = {
            "input_file": input_file,
            "output_dir": output_dir,
            "namespace": namespace,
            "parameters": params,
            "dry_run": job["global_parameters"].get("dry_run", False),
        }
        config_file = self.jobs_dir / f"{job['id']}_config.json"
        with open(config_file, "w") as f:
            json.dump(config, f)

        # Build command to call worker script
        cmd = [
            "python", "app/worker.py",
            str(config_file),
        ]

        try:
            # Create log file for this subprocess
            log_file = self.jobs_dir / f"{job['id']}_subprocess.log"

            # Spawn process with output captured to log file
            with open(log_file, "w") as log:
                process = subprocess.Popen(
                    cmd,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )

            file_info["status"] = "running"
            file_info["progress"] = 0.5  # In progress
            file_info["log_file"] = str(log_file)
            job["pid"] = process.pid
            job["status"] = "running"
            job["started_at"] = datetime.utcnow().isoformat() + "Z"

        except Exception as e:
            file_info["status"] = "failed"
            file_info["error"] = f"Failed to spawn: {str(e)}"
