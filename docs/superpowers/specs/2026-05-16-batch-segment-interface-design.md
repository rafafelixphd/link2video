# Segment Batch Processor Web Interface — Design Spec

**Date:** 2026-05-16  
**Project:** link2video  
**Scope:** Web interface for batch processing of the `segment` CLI functionality

---

## Overview

A simple Flask web app that allows batch processing of multiple video/audio files through the `segment` functionality without requiring CLI commands. Users can:
- Add multiple files from anywhere on the computer
- Configure segment parameters globally or per-file
- Submit batch jobs that run asynchronously in the background
- Close the browser and return later to check job status
- Cancel running jobs

**Tech stack:** Flask (backend) + HTML/Jinja templates + vanilla JavaScript (frontend) + JSON-based job persistence

---

## Architecture

### Directory Structure

```
link2video/                     (project root)
├── link2video/                 (package)
│   ├── auto/
│   │   ├── split/
│   │   │   ├── base.py
│   │   │   └── silent/
│   │   ├── extract_audio/
│   │   ├── transcribe/
│   │   └── __init__.py
│   ├── main.py
│   └── __init__.py
├── app/                        (web application - separate from package)
│   ├── app.py                  (Flask routes)
│   ├── job_manager.py          (job queue and process management)
│   ├── .jobs/                  (job persistence - git-ignored)
│   │   ├── 20260516_143022_abc123.json
│   │   └── ...
│   └── templates/
│       ├── base.html
│       ├── index.html
│       └── static/
│           └── style.css
├── web_ui_launch.py            (entry point - starts Flask server)
├── .gitignore                  (updated to include app/.jobs/)
└── ...
```

### Stack Choices

- **Backend:** Flask (simple, lightweight, minimal dependencies)
- **Frontend:** Server-rendered HTML + Jinja templates + minimal vanilla JS (no build tools, no Node.js required)
- **Job persistence:** JSON files in `app/.jobs/` (human-readable, debuggable, no external database)
- **Process management:** Python `subprocess` module with PID tracking
- **Module integration:** Direct Python imports from `link2video.auto.split.silent` (no CLI subprocess calls)
- **Status polling:** Browser polls backend every 2 seconds (simple, reliable)

---

## User Interface

### Single-Page Layout (Table-Based)

The interface has three tabs (Segment, Extract Audio, Transcribe) with placeholders. Only the **Segment** tab is implemented.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Batch Processor                                    [Refresh]        │
├─────────────────────────────────────────────────────────────────────┤
│ [Segment]  [Extract Audio]  [Transcribe]                            │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  INPUT FILES & PARAMETERS                                           │
│  [+ Add Files]  Output Dir: [/path/to/output]  Job Concurrency: [2] │
│  [Dry Run ☐]  [Process]                                            │
│                                                                      │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ File         │Namespace│Threshold│Quiet│Pad│Thread│Skip│Rem  │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │video1.mp4    │video1   │ -10dB   │3.5  │1.0│ 2   │1.5 │ [X] │ │
│  │video2.mp4    │video2   │ -10dB   │3.5  │1.0│ 2   │1.5 │ [X] │ │
│  │presentation  │pres     │ -10dB   │3.5  │1.0│ 2   │1.5 │ [X] │ │
│  │ .mov         │         │         │     │   │     │    │     │ │
│  └────────────────────────────────────────────────────────────────┘ │
│                                                                      │
│  ACTIVE JOBS                                                        │
│  ┌────────────────────────────────────────────────────────────────┐ │
│  │ File         │ Status    │ Progress    │ Segments │ Action   │ │
│  ├────────────────────────────────────────────────────────────────┤ │
│  │video1.mp4    │ Running   │ [████░░] 60%│ -        │ [Cancel] │ │
│  │video2.mp4    │ Running   │ [██░░░░] 30%│ -        │ [Cancel] │ │
│  │presentation  │ Complete  │ ✓           │ 5        │ [View]   │ │
│  │ .mov         │           │             │          │          │ │
│  └────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Segment Tab Specifics

**Input Files Section:**
- `[+ Add Files]` — Opens native file picker; user can select multiple files from any directory
- Table columns: File (path), Namespace, Threshold, Quiet For, Padding, Threads, Skip Shorter, Remove
- User can click any cell to edit (except File path)
- Namespace auto-populated from filename (e.g., `video1.mp4` → namespace `video1`), but editable
- Default parameters (Threshold, Quiet For, Padding, Threads, Skip Shorter) apply to all files
- Each file can override any parameter by clicking that cell
- `[X]` removes file from input list

**Output Configuration:**
- Output Dir: shows current path, user can click to browse and select a new directory
- Job Concurrency: number of segment jobs to run in parallel (e.g., 2 means 2 files process simultaneously, others queue)
- Dry Run checkbox: if checked, jobs preview changes without creating files

**Process Button:**
- `[Process]` submits the batch, creates a job, queues files for processing

**Active Jobs Section:**
- Lists all running and recently completed jobs
- Columns: File, Status (Pending/Running/Complete/Failed), Progress (%, progress bar), Segments Created, Actions
- `[Cancel]` stops a running job
- `[View]` opens output directory in file explorer (uses `open` on Mac, `explorer` on Windows, `xdg-open` on Linux)

---

## Job Management & Backend

### Job Lifecycle

1. **User submits batch** → Job created with unique ID based on timestamp (e.g., `20260516_143022_abc123`)
2. **Job JSON written** → Stored in `app/.jobs/` with initial state `pending`
3. **Job queue checks** → Backend's job manager scans for pending jobs
4. **Concurrency check** → When a slot opens (respecting `job_concurrency` limit), state changes to `running`
5. **Process spawns** → Calls `SilenceSplitter.split()` with provided parameters
6. **Job progresses** → Polls process output to update progress percentage
7. **Job completes** → State changes to `completed` or `failed`, PID cleared
8. **Persistence** → Job JSON stays on disk indefinitely (for history/debugging)

### Job JSON Structure

**File:** `app/.jobs/20260516_143022_abc123.json`

```json
{
  "id": "20260516_143022_abc123",
  "tab": "segment",
  "created_at": "2026-05-16T14:30:22Z",
  "started_at": "2026-05-16T14:30:25Z",
  "completed_at": null,
  "status": "running",
  "pid": 12345,
  "files": [
    {
      "input": "/Users/rafafelix/Videos/video1.mp4",
      "namespace": "video1",
      "output_dir": "/Users/rafafelix/segments",
      "parameters": {
        "threshold": "-10dB",
        "quiet_for": 3.5,
        "padding": 1.0,
        "threads": 2,
        "skip_shorter": 1.5
      },
      "status": "running",
      "progress": 0.65,
      "segments_created": 0,
      "error": null,
      "stdout": "",
      "stderr": ""
    },
    {
      "input": "/Users/rafafelix/Videos/video2.mp4",
      "namespace": "video2",
      "output_dir": "/Users/rafafelix/segments",
      "parameters": {
        "threshold": "-10dB",
        "quiet_for": 3.5,
        "padding": 1.0,
        "threads": 2,
        "skip_shorter": 1.5
      },
      "status": "pending",
      "progress": 0,
      "segments_created": 0,
      "error": null,
      "stdout": "",
      "stderr": ""
    }
  ],
  "global_parameters": {
    "job_concurrency": 2,
    "dry_run": false
  }
}
```

### Job Manager (`app/job_manager.py`)

Responsibilities:
- **Startup:** Scan `app/.jobs/` for all jobs; identify running/pending jobs
- **Resumption:** For jobs with PIDs, check if process still alive; if yes, re-attach; if no, mark as `failed`
- **Queueing:** Maintain queue of pending files across all jobs
- **Concurrency:** Respect global `job_concurrency` limit; spawn next file when slot opens
- **Execution:** Call `SilenceSplitter.split()` directly with parameters from job JSON
- **Monitoring:** Poll running process, capture stdout/stderr, update progress, update job JSON
- **Completion:** Mark file/job as `completed` or `failed` with error details

---

## API Endpoints

### REST API

```
GET  /                          # Serve HTML page (index.html)
GET  /api/jobs                  # Return JSON list of all jobs (running + completed)
POST /api/jobs                  # Create new batch job (receive JSON with files, params)
GET  /api/jobs/<job_id>         # Get single job status (JSON)
DELETE /api/jobs/<job_id>       # Cancel job (set status to "cancelled")
POST /api/files/browse          # Browse filesystem for file/directory picker (returns dirs/files)
```

### Response Examples

**GET /api/jobs** — List all jobs:
```json
{
  "jobs": [
    {
      "id": "20260516_143022_abc123",
      "status": "running",
      "created_at": "2026-05-16T14:30:22Z",
      "files_count": 2,
      "completed_count": 0,
      "failed_count": 0
    },
    {
      "id": "20260516_140000_def456",
      "status": "completed",
      "created_at": "2026-05-16T14:00:00Z",
      "files_count": 1,
      "completed_count": 1,
      "failed_count": 0
    }
  ]
}
```

**GET /api/jobs/<job_id>** — Job detail:
```json
{
  "id": "20260516_143022_abc123",
  "status": "running",
  "files": [
    {
      "input": "/path/to/video1.mp4",
      "namespace": "video1",
      "status": "running",
      "progress": 0.65,
      "segments_created": 0,
      "error": null
    },
    {
      "input": "/path/to/video2.mp4",
      "namespace": "video2",
      "status": "pending",
      "progress": 0,
      "segments_created": 0,
      "error": null
    }
  ]
}
```

---

## Frontend Implementation

### Entry Point (`web_ui_launch.py`)

```python
#!/usr/bin/env python3
import sys
from app.app import app

if __name__ == "__main__":
    print("Starting Batch Processor at http://localhost:5000")
    app.run(debug=False, host="127.0.0.1", port=5000)
```

User runs: `python web_ui_launch.py` (or can be wrapped in a shell script)

### HTML Template (`app/templates/index.html`)

- Form with file input (native file picker)
- Output directory input (native directory picker)
- Parameter inputs (threshold, quiet-for, padding, threads, skip-shorter, job-concurrency)
- Tables rendered with Jinja loops
- Minimal JavaScript for:
  - Form submission (POST /api/jobs)
  - Poll loop (GET /api/jobs every 2 seconds)
  - Cell editing (synchronous, no backend)
  - Cancel/View actions

### JavaScript Polling

```javascript
setInterval(async () => {
  const response = await fetch('/api/jobs');
  const data = await response.json();
  updateJobsTable(data.jobs);
}, 2000);
```

---

## Error Handling

### Common Scenarios

| Scenario | Handling |
|----------|----------|
| File not found | Job marked `failed`, error message stored in job JSON |
| Invalid parameter (e.g., bad threshold) | Caught before job creation, error shown in UI |
| Process crashes | Job marked `failed`, stderr captured |
| Disk full | Process fails, error captured |
| User closes browser | No impact; job continues in background |
| Process PID stale on startup | Process check fails, job marked `failed` |

### Error Messages

Errors are stored in job JSON under `files[].error` and displayed in the UI next to the job status.

---

## Startup Behavior

**On server start:**
1. Scan `app/.jobs/` for all job files
2. For each job:
   - If status is `running` and PID exists: check if process alive
     - If alive: continue tracking it
     - If dead: mark job as `failed`
   - If status is `pending`: add files to queue
3. Start job queue processor (respects concurrency, spawns processes)
4. Start Flask server on `http://localhost:5000`

**On browser load:**
1. Fetch `/api/jobs` to get current job list
2. Render jobs table with statuses
3. Start polling loop (every 2 seconds)

---

## Future Extensions

- **Extract Audio tab** — Same pattern, calls `ExtractAudioProcessor.extract()`
- **Transcribe tab** — Same pattern, calls `TranscribeProcessor.transcribe()`
- **Job history cleanup** — Option to archive/delete old job files
- **Progress granularity** — Track segment count as it increases (more detailed progress)
- **Notifications** — Desktop notifications when jobs complete

---

## Success Criteria

1. ✓ Web interface accessible at `http://localhost:5000`
2. ✓ Multi-file input with add/remove UI
3. ✓ Per-file namespace auto-generated from filename with override capability
4. ✓ Per-file parameter override for segment settings
5. ✓ Global job concurrency setting
6. ✓ Jobs run asynchronously in background
7. ✓ Job state persists to disk in `app/.jobs/`
8. ✓ Browser can close and reopen; jobs continue and status is visible
9. ✓ Users can cancel running jobs
10. ✓ Simple, clean table-based UI (no fancy styling)
11. ✓ Error messages captured and displayed
12. ✓ Tab placeholders for Extract Audio and Transcribe (no implementation yet)

---

## Testing Strategy

- ✓ Add multiple files; verify they appear in table with correct namespaces
- ✓ Edit parameters; verify changes persist per-file
- ✓ Submit batch; verify jobs created and appear in Active Jobs table
- ✓ Verify processes run (check output directory for segments)
- ✓ Close browser; reopen; verify job statuses still visible
- ✓ Cancel running job; verify process stops
- ✓ Test error handling (invalid paths, permission denied, etc.)
- ✓ Test concurrency limit (submit 3 files with concurrency=2; verify 2 run, 1 queues)
