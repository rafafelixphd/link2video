# Batch Processor App — Refactor Design

## Goal

Refactor the `app/` Flask backend from a mess of nested closures, subprocess hacks, and PID polling into a clean, properly separated web API that uses `link2video` as an installed package.

No functionality changes. Same behaviour, clean structure.

---

## Problems Being Fixed

| File | Problem |
|---|---|
| `app/app.py` | All routes defined as nested closures inside `create_app()` |
| `app/app.py` | Startup recovery logic mixed into the factory function |
| `app/app.py` | try/except import hack for relative vs absolute imports |
| `app/launch.py` | Stale comment, unused `import sys` and `import os` |
| `app/job_manager.py` | Uses `subprocess.Popen` + PID polling instead of the library |
| `app/job_manager.py` | Hardcoded `"python", "app/worker.py"` relative path |
| `app/worker.py` | Exists only to work around the subprocess hack — to be deleted |

---

## Target File Structure

```
app/
├── launch.py       # Entry point only: argparse, banner, app.run()
├── factory.py      # create_app(): registers Blueprint, middleware, calls recover()
├── routes.py       # Flask Blueprint: all route handlers, reads job_manager from app.config
├── job_manager.py  # JobManager: ProcessPoolExecutor, self-reporting via JSON
└── templates/      # Unchanged
```

`app/app.py` and `app/worker.py` are deleted.

---

## Architecture

### `launch.py`
Single responsibility: parse args, print banner, call `app.run()`. Imports `create_app` from `factory.py`. No unused imports.

### `factory.py`
Single responsibility: build the Flask app. Creates `JobManager`, calls `job_manager.recover()` on startup, stores it in `app.config["JOB_MANAGER"]`, registers the Blueprint, registers `before_request` tick.

### `routes.py`
Single responsibility: HTTP interface. A Flask Blueprint. All route handlers live here. Access the job manager via `current_app.config["JOB_MANAGER"]`.

### `job_manager.py`

The core change. Three parts:

**1. `run_split()` — module-level function (required for pickling)**

Called inside a `ProcessPoolExecutor` worker process. Takes `job_id`, `file_index`, `jobs_dir`, and all file parameters. Writes status directly to the job JSON at each transition:
- Sets file status `"running"` on entry
- Sets file status `"completed"` with segment count on success
- Sets file status `"failed"` with error message on exception

**2. `_update_file_status()` — module-level helper**

Called by `run_split()`. Opens the job JSON, updates the file at `file_index`, writes back. Best-effort: silently swallows IO errors (can't do anything useful from a subprocess).

**3. `JobManager` class**

- Holds a `ProcessPoolExecutor(max_workers=8)` instance
- Holds a `_futures: Dict[tuple, Future]` mapping `(job_id, file_index)` → `Future`
- `recover()`: called on startup, resets files stuck in `"running"` to `"failed"` with message `"Server restarted"`
- `process_queue()`: prune done futures → `_update_all_job_statuses()` → `_spawn_pending_files()`
- `_spawn_pending_files()`: counts `running_count` from live futures (not PIDs), submits new work via `executor.submit()`
- `cancel_job()`: calls `future.cancel()` (works if pending), deletes JSON regardless
- `_delete_job()`: deletes only the job JSON — no more log files or config files
- **Deleted**: `_monitor_running_processes()`, `_job_has_running_pid()`, `_spawn_subprocess()`

---

## JSON Schema Changes

`pid` field removed. `log_file` field removed. File entries are now written by the process itself.

```json
{
  "id": "20260523_120000_abc12345",
  "status": "running",
  "created_at": "...",
  "started_at": "...",
  "completed_at": null,
  "files": [
    {
      "input": "/path/to/video.mp4",
      "namespace": "video",
      "output_dir": "/path/to/output",
      "parameters": { "threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 2, "skip_shorter": 3.0 },
      "status": "completed",
      "segments_created": 5,
      "progress": 1.0,
      "error": null
    }
  ],
  "global_parameters": { "job_concurrency": 2, "dry_run": false }
}
```
