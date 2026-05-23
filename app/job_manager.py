"""
Job queue and process manager for batch segment processing.

Module-level functions (run_split, _update_file_status) run inside
ProcessPoolExecutor worker processes and self-report status to JSON.
"""
import json
import os
import uuid
from concurrent.futures import ProcessPoolExecutor, Future
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from link2video.auto.split.silent import SilenceSplitter


# ---------------------------------------------------------------------------
# Module-level worker functions (must be at module level for pickling)
# ---------------------------------------------------------------------------

def _update_file_status(
    jobs_dir: str,
    job_id: str,
    file_index: int,
    status: str,
    segments: int = 0,
    error: Optional[str] = None,
) -> None:
    """Write file status update to the job JSON. Called from worker process."""
    job_file = Path(jobs_dir) / f"{job_id}.json"
    try:
        with open(job_file) as f:
            job = json.load(f)

        file_info = job["files"][file_index]
        file_info["status"] = status

        if status == "running":
            job["status"] = "running"
            if not job.get("started_at"):
                job["started_at"] = datetime.now(timezone.utc).isoformat()
        elif status == "completed":
            file_info["segments_created"] = segments
            file_info["progress"] = 1.0
        elif status == "failed":
            file_info["error"] = error

        with open(job_file, "w") as f:
            json.dump(job, f, indent=2)
    except Exception:
        pass  # Best-effort — can't recover from write failure in a subprocess


def run_split(
    job_id: str,
    file_index: int,
    jobs_dir: str,
    input_file: str,
    output_dir: str,
    namespace: str,
    params: Dict[str, Any],
    dry_run: bool,
) -> None:
    """
    Run SilenceSplitter for one file. Executed in a ProcessPoolExecutor worker.

    Self-reports status transitions directly to the job JSON:
      pending -> running -> completed | failed
    """
    _update_file_status(jobs_dir, job_id, file_index, "running")
    try:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        splitter = SilenceSplitter()
        segments = splitter.split(
            input_file=input_file,
            output_dir=output_dir,
            namespace=namespace,
            threshold=params.get("threshold", "-10dB"),
            quiet_for=params.get("quiet_for", 3.5),
            padding=params.get("padding", 1.0),
            threads=params.get("threads", 2),
            skip_shorter=params.get("skip_shorter", 3.0),
            dry_run=dry_run,
        )
        _update_file_status(jobs_dir, job_id, file_index, "completed", segments=len(segments))
    except Exception as exc:
        _update_file_status(jobs_dir, job_id, file_index, "failed", error=str(exc))


# ---------------------------------------------------------------------------
# JobManager
# ---------------------------------------------------------------------------

class JobManager:
    """Manages job queue, persistence, and process execution."""

    def __init__(self, jobs_dir: str = "app/.jobs") -> None:
        self.jobs_dir = Path(jobs_dir)
        self.jobs_dir.mkdir(parents=True, exist_ok=True)
        self._executor = ProcessPoolExecutor(max_workers=8)
        self._futures: Dict[Tuple[str, int], Future] = {}

    def recover(self) -> None:
        """Reset files stuck in 'running' state on server restart."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                if job["status"] != "running":
                    continue
                for file_info in job["files"]:
                    if file_info["status"] == "running":
                        file_info["status"] = "failed"
                        file_info["error"] = "Failed: server restarted while processing"
                self._update_job_status(job)
                with open(job_file, "w") as f:
                    json.dump(job, f, indent=2)
            except (json.JSONDecodeError, KeyError):
                pass

    def create_job(self, files: List[Dict[str, Any]], global_params: Dict[str, Any]) -> str:
        """Create a new batch job and persist to disk."""
        job_id = self._generate_job_id()
        job_data = {
            "id": job_id,
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "started_at": None,
            "completed_at": None,
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
        """Return summary list of all jobs, newest first."""
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
        """Cancel pending future if possible, delete job from disk."""
        if not self.get_job(job_id):
            return False
        for key in list(self._futures.keys()):
            if key[0] == job_id:
                self._futures[key].cancel()
                del self._futures[key]
        self._delete_job(job_id)
        return True

    def clear_all_jobs(self) -> None:
        """Cancel all futures and delete all job files."""
        for future in self._futures.values():
            future.cancel()
        self._futures.clear()
        for job_file in list(self.jobs_dir.glob("*.json")):
            job_file.unlink(missing_ok=True)

    def process_queue(self) -> None:
        """Called on each Flask request. Prune futures, sync statuses, spawn work."""
        self._futures = {k: v for k, v in self._futures.items() if not v.done()}
        self._update_all_job_statuses()
        self._spawn_pending_files()

    def _spawn_pending_files(self) -> None:
        """Submit pending files to the executor, respecting concurrency limit."""
        running_count = len(self._futures)

        job_concurrency = 2
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                if job["status"] in ("pending", "running"):
                    job_concurrency = min(job["global_parameters"].get("job_concurrency", 2), 8)
                    break
            except (json.JSONDecodeError, KeyError):
                pass

        if running_count >= job_concurrency:
            return

        for job_file in sorted(self.jobs_dir.glob("*.json")):
            try:
                with open(job_file) as f:
                    job = json.load(f)

                if job["status"] not in ("pending", "running"):
                    continue

                for file_index, file_info in enumerate(job["files"]):
                    if file_info["status"] != "pending":
                        continue

                    if not Path(file_info["input"]).is_file():
                        file_info["status"] = "failed"
                        file_info["error"] = f"File not found: {file_info['input']}"
                        self._update_job_status(job)
                        self._persist_job(job["id"], job)
                        return

                    future = self._executor.submit(
                        run_split,
                        job_id=job["id"],
                        file_index=file_index,
                        jobs_dir=str(self.jobs_dir),
                        input_file=file_info["input"],
                        output_dir=file_info["output_dir"],
                        namespace=file_info["namespace"],
                        params=file_info["parameters"],
                        dry_run=job["global_parameters"].get("dry_run", False),
                    )
                    self._futures[(job["id"], file_index)] = future
                    return

            except (json.JSONDecodeError, KeyError):
                pass

    def _update_job_status(self, job: Dict[str, Any]) -> None:
        """Recalculate job status from its file statuses."""
        statuses = [f["status"] for f in job["files"]]
        if all(s == "completed" for s in statuses):
            job["status"] = "completed"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
        elif all(s in ("failed", "cancelled") for s in statuses):
            job["status"] = "failed"
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
        elif any(s == "running" for s in statuses):
            job["status"] = "running"
        else:
            job["status"] = "pending"

    def _update_all_job_statuses(self) -> None:
        """Re-read each active job from disk and sync its status."""
        for job_file in self.jobs_dir.glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                if job["status"] in ("completed", "failed", "cancelled"):
                    continue
                self._update_job_status(job)
                self._persist_job(job["id"], job)
            except (json.JSONDecodeError, KeyError):
                pass

    def _persist_job(self, job_id: str, job_data: Dict[str, Any]) -> None:
        """Write job state to disk."""
        job_file = self.jobs_dir / f"{job_id}.json"
        with open(job_file, "w") as f:
            json.dump(job_data, f, indent=2)

    def _delete_job(self, job_id: str) -> None:
        """Delete job JSON from disk."""
        job_file = self.jobs_dir / f"{job_id}.json"
        job_file.unlink(missing_ok=True)

    def _generate_job_id(self) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        return f"{timestamp}_{uuid.uuid4().hex[:8]}"
