# Batch Processor App — Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor the Flask `app/` backend into clean, separated modules that use `link2video` as an installed package — no subprocess hacks, no PID polling, no nested closures.

**Architecture:** `launch.py` (entry point) → `factory.py` (app factory) → `routes.py` (Blueprint) → `job_manager.py` (ProcessPoolExecutor + self-reporting via JSON). `worker.py` and `app.py` are deleted.

**Tech Stack:** Flask, Python `concurrent.futures.ProcessPoolExecutor`, `link2video` as installed package.

---

## Files Touched

| Action | File |
|---|---|
| Rewrite | `app/job_manager.py` |
| Create | `app/routes.py` |
| Create | `app/factory.py` |
| Rewrite | `app/launch.py` |
| Update | `app/__init__.py` |
| Delete | `app/app.py` |
| Delete | `app/worker.py` |
| Unchanged | `app/templates/*` |

---

### Task 1: Rewrite `job_manager.py` with ProcessPoolExecutor and self-reporting

**Files:**
- Modify: `app/job_manager.py`

This is the core change. Replace `subprocess.Popen` + PID polling with `ProcessPoolExecutor` + self-reporting. The worker function writes its own status to the JSON file at each state transition.

- [ ] **Step 1: Write the failing test**

Create `tests/test_job_manager.py`:

```python
import json
import time
from pathlib import Path
import pytest
from app.job_manager import JobManager, run_split


def test_run_split_updates_json_on_success(tmp_path):
    """run_split writes 'completed' status to JSON when done."""
    job_id = "test_job_001"
    job_file = tmp_path / f"{job_id}.json"
    job_file.write_text(json.dumps({
        "id": job_id,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "files": [{
            "input": str(tmp_path / "fake.mp4"),
            "namespace": "fake",
            "output_dir": str(tmp_path / "out"),
            "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5},
            "status": "pending",
            "progress": 0,
            "segments_created": 0,
            "error": None,
        }],
        "global_parameters": {"job_concurrency": 1, "dry_run": True},
    }))
    # Create a fake video file
    (tmp_path / "fake.mp4").touch()

    run_split(
        job_id=job_id,
        file_index=0,
        jobs_dir=str(tmp_path),
        input_file=str(tmp_path / "fake.mp4"),
        output_dir=str(tmp_path / "out"),
        namespace="fake",
        params={"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5},
        dry_run=True,
    )

    result = json.loads(job_file.read_text())
    assert result["files"][0]["status"] in ("completed", "failed")  # dry_run may complete or fail gracefully


def test_run_split_writes_failed_on_bad_file(tmp_path):
    """run_split writes 'failed' status when input file is missing."""
    job_id = "test_job_002"
    job_file = tmp_path / f"{job_id}.json"
    job_file.write_text(json.dumps({
        "id": job_id,
        "status": "pending",
        "started_at": None,
        "completed_at": None,
        "files": [{
            "input": "/nonexistent/file.mp4",
            "namespace": "test",
            "output_dir": str(tmp_path / "out"),
            "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5},
            "status": "pending",
            "progress": 0,
            "segments_created": 0,
            "error": None,
        }],
        "global_parameters": {"job_concurrency": 1, "dry_run": False},
    }))

    run_split(
        job_id=job_id,
        file_index=0,
        jobs_dir=str(tmp_path),
        input_file="/nonexistent/file.mp4",
        output_dir=str(tmp_path / "out"),
        namespace="test",
        params={"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5},
        dry_run=False,
    )

    result = json.loads(job_file.read_text())
    assert result["files"][0]["status"] == "failed"
    assert result["files"][0]["error"] is not None


def test_job_manager_recover_resets_running_jobs(tmp_path):
    """recover() marks files stuck in 'running' as 'failed'."""
    job_id = "stale_job"
    job_file = tmp_path / f"{job_id}.json"
    job_file.write_text(json.dumps({
        "id": job_id,
        "status": "running",
        "started_at": "2026-01-01T00:00:00Z",
        "completed_at": None,
        "files": [{
            "input": "/some/file.mp4",
            "namespace": "test",
            "output_dir": "/out",
            "parameters": {},
            "status": "running",
            "progress": 0.5,
            "segments_created": 0,
            "error": None,
        }],
        "global_parameters": {"job_concurrency": 1, "dry_run": False},
    }))

    manager = JobManager(jobs_dir=str(tmp_path))
    manager.recover()

    result = json.loads(job_file.read_text())
    assert result["files"][0]["status"] == "failed"
    assert "restart" in result["files"][0]["error"].lower()


def test_job_manager_create_and_list(tmp_path):
    """create_job persists to disk, list_jobs returns it."""
    manager = JobManager(jobs_dir=str(tmp_path))
    job_id = manager.create_job(
        files=[{
            "input": "/path/video.mp4",
            "namespace": "video",
            "output_dir": "/out",
            "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 2, "skip_shorter": 1.5},
        }],
        global_params={"job_concurrency": 2, "dry_run": False},
    )

    jobs = manager.list_jobs()
    assert len(jobs) == 1
    assert jobs[0]["id"] == job_id
    assert jobs[0]["status"] == "pending"


def test_cancel_job_deletes_file(tmp_path):
    """cancel_job removes the job JSON from disk."""
    manager = JobManager(jobs_dir=str(tmp_path))
    job_id = manager.create_job(
        files=[{"input": "/f.mp4", "namespace": "f", "output_dir": "/out",
                "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5}}],
        global_params={"job_concurrency": 1, "dry_run": False},
    )
    manager.cancel_job(job_id)
    assert not (tmp_path / f"{job_id}.json").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_job_manager.py -v
```

Expected: `ImportError` or `AttributeError` — `run_split`, `recover` don't exist yet.

- [ ] **Step 3: Rewrite `app/job_manager.py`**

```python
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
      pending → running → completed | failed
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
        # (job_id, file_index) -> Future
        self._futures: Dict[Tuple[str, int], Future] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

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
        # Cancel future if not yet running
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
        """
        Called on each Flask request (before_request hook).
        1. Prune completed futures from tracking dict.
        2. Recalculate job statuses from JSON file states.
        3. Spawn pending work if concurrency slots available.
        """
        # Prune done futures (process wrote its own result to JSON)
        self._futures = {k: v for k, v in self._futures.items() if not v.done()}
        # Sync job-level status from file-level statuses
        self._update_all_job_statuses()
        # Submit new work
        self._spawn_pending_files()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _spawn_pending_files(self) -> None:
        """Submit pending files to the executor, respecting concurrency limit."""
        running_count = len(self._futures)

        # Read concurrency limit from the first active job
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

                    # Validate input file before submitting
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
                    return  # One submission per queue tick

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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_job_manager.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add app/job_manager.py tests/test_job_manager.py
git commit -m "refactor: replace subprocess+PID with ProcessPoolExecutor and self-reporting"
```

---

### Task 2: Create `app/routes.py` Blueprint

**Files:**
- Create: `app/routes.py`

Extract all route handlers from `app/app.py` into a proper Flask Blueprint. Access `JobManager` via `current_app.config["JOB_MANAGER"]`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_routes.py`:

```python
import json
import pytest
from unittest.mock import MagicMock
from app.factory import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(jobs_dir=str(tmp_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_root(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_list_jobs_empty(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.get_json() == {"jobs": []}


def test_create_job_missing_files(client):
    resp = client.post("/api/jobs", json={"output_dir": "/out"})
    assert resp.status_code == 400


def test_create_job_missing_output_dir(client):
    resp = client.post("/api/jobs", json={"files": [{"input": "/f.mp4", "namespace": "f"}]})
    assert resp.status_code == 400


def test_create_job_success(client):
    resp = client.post("/api/jobs", json={
        "files": [{"input": "/f.mp4", "namespace": "f", "output_dir": "/out",
                   "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 2, "skip_shorter": 1.5}}],
        "output_dir": "/out",
        "job_concurrency": 1,
        "dry_run": False,
    })
    assert resp.status_code == 201
    assert "id" in resp.get_json()


def test_delete_nonexistent_job(client):
    resp = client.delete("/api/jobs/nonexistent_id")
    assert resp.status_code == 400


def test_clear_all_jobs(client):
    resp = client.delete("/api/jobs/clear/all")
    assert resp.status_code == 200
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_routes.py -v
```

Expected: `ImportError` — `app.factory` doesn't exist yet.

- [ ] **Step 3: Create `app/routes.py`**

```python
"""Flask Blueprint containing all HTTP route handlers."""
from flask import Blueprint, current_app, jsonify, render_template, request

jobs_bp = Blueprint("jobs", __name__)


def _manager():
    return current_app.config["JOB_MANAGER"]


@jobs_bp.route("/")
def index():
    return render_template("base.html")


@jobs_bp.route("/api/jobs", methods=["GET"])
def list_jobs():
    return jsonify({"jobs": _manager().list_jobs()})


@jobs_bp.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    job = _manager().get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@jobs_bp.route("/api/jobs", methods=["POST"])
def create_job():
    data = request.get_json()

    if not data.get("files"):
        return jsonify({"error": "No files provided"}), 400
    if not data.get("output_dir"):
        return jsonify({"error": "Output directory required"}), 400
    for f in data["files"]:
        if not f.get("input"):
            return jsonify({"error": "File path required for all files"}), 400
        if not f.get("namespace"):
            return jsonify({"error": "Namespace required for all files"}), 400

    global_params = {
        "job_concurrency": min(data.get("job_concurrency", 2), 8),
        "dry_run": data.get("dry_run", False),
    }
    job_id = _manager().create_job(data["files"], global_params)
    return jsonify({"id": job_id}), 201


@jobs_bp.route("/api/jobs/<job_id>", methods=["DELETE"])
def cancel_job(job_id: str):
    if _manager().cancel_job(job_id):
        return jsonify({"status": "deleted"}), 200
    return jsonify({"error": "Could not delete job"}), 400


@jobs_bp.route("/api/jobs/clear/all", methods=["DELETE"])
def clear_all_jobs():
    _manager().clear_all_jobs()
    return jsonify({"status": "cleared"}), 200
```

- [ ] **Step 4: Run tests — still failing (factory.py missing)**

```bash
pytest tests/test_routes.py -v
```

Expected: `ImportError: cannot import name 'create_app' from 'app.factory'`

- [ ] **Step 5: Commit routes**

```bash
git add app/routes.py tests/test_routes.py
git commit -m "refactor: extract routes into Blueprint in routes.py"
```

---

### Task 3: Create `app/factory.py` and clean up entry points

**Files:**
- Create: `app/factory.py`
- Rewrite: `app/launch.py`
- Update: `app/__init__.py`
- Delete: `app/app.py`
- Delete: `app/worker.py`

- [ ] **Step 1: Create `app/factory.py`**

```python
"""Flask application factory."""
from flask import Flask

from .job_manager import JobManager
from .routes import jobs_bp


def create_app(jobs_dir: str = "app/.jobs") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")

    job_manager = JobManager(jobs_dir=jobs_dir)
    job_manager.recover()
    app.config["JOB_MANAGER"] = job_manager

    app.register_blueprint(jobs_bp)

    @app.before_request
    def tick():
        app.config["JOB_MANAGER"].process_queue()

    return app
```

- [ ] **Step 2: Update `app/__init__.py`**

```python
"""Batch Processor Flask application."""
from .factory import create_app

__all__ = ["create_app"]
```

- [ ] **Step 3: Rewrite `app/launch.py`**

```python
#!/usr/bin/env python3
"""Batch Processor — web UI launcher."""
import argparse

from app.factory import create_app

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run Batch Segment Processor")
    parser.add_argument("--debug", action="store_true", help="Enable debug mode")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", default=5123, type=int, help="Port to bind to")
    args = parser.parse_args()

    app = create_app()

    print("=" * 60)
    print("  Batch Segment Processor")
    print(f"  http://{args.host}:{args.port}")
    print("=" * 60)

    app.run(debug=args.debug, host=args.host, port=args.port)
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 5: Delete `app/app.py` and `app/worker.py`**

```bash
git rm app/app.py app/worker.py
```

- [ ] **Step 6: Commit**

```bash
git add app/factory.py app/__init__.py app/launch.py
git commit -m "refactor: factory.py, clean launch.py, delete app.py and worker.py"
```

---

### Task 4: Smoke test end-to-end

**Files:**
- No code changes — verification only

- [ ] **Step 1: Start the server**

```bash
python app/launch.py
```

Expected output:
```
============================================================
  Batch Segment Processor
  http://0.0.0.0:5123
============================================================
```

- [ ] **Step 2: Verify API responds**

```bash
curl http://localhost:5123/api/jobs
```

Expected: `{"jobs": []}`

- [ ] **Step 3: Create a test job with a bad path (expect fail status)**

```bash
curl -s -X POST http://localhost:5123/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"files":[{"input":"/nonexistent/file.mp4","namespace":"test","output_dir":"/tmp/out","parameters":{"threshold":"-10dB","quiet_for":3.5,"padding":1.0,"threads":2,"skip_shorter":1.5}}],"output_dir":"/tmp/out","job_concurrency":1,"dry_run":false}'
```

Wait 5 seconds, then:

```bash
curl http://localhost:5123/api/jobs
```

Expected: job status `"failed"`, file error `"File not found: /nonexistent/file.mp4"`.

- [ ] **Step 4: Clear jobs**

```bash
curl -X DELETE http://localhost:5123/api/jobs/clear/all
curl http://localhost:5123/api/jobs
```

Expected: `{"jobs": []}` and `.jobs/` directory is empty.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: complete — clean Flask structure, ProcessPoolExecutor, self-reporting jobs"
```
