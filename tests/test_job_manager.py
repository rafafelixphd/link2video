import json
import time
from pathlib import Path
import pytest
from app.job_manager import JobManager, run_split


def test_run_split_updates_json_on_success(tmp_path):
    """run_split writes 'completed' status to JSON when SilenceSplitter succeeds."""
    from unittest.mock import patch

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
        "global_parameters": {"job_concurrency": 1, "dry_run": False},
    }))
    (tmp_path / "fake.mp4").touch()

    with patch("app.job_manager.SilenceSplitter") as mock_splitter:
        mock_splitter.return_value.split.return_value = []
        run_split(
            job_id=job_id,
            file_index=0,
            jobs_dir=str(tmp_path),
            input_file=str(tmp_path / "fake.mp4"),
            output_dir=str(tmp_path / "out"),
            namespace="fake",
            params={"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 1, "skip_shorter": 1.5},
            dry_run=False,
        )

    result = json.loads(job_file.read_text())
    assert result["files"][0]["status"] == "completed"
    assert result["files"][0]["segments_created"] == 0


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
