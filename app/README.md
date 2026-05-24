# Batch Segment Processor Web Interface

A Flask web application for batch-processing multiple video/audio files through the `segment` functionality without requiring CLI commands.

## Quick Start

### Launch the server:

```bash
python web_ui_launch.py
```

The app will start at `http://localhost:5000`

### Using the web interface:

1. **Add files** — Click `[+ Add Files]` to select one or more video/audio files from your computer
2. **Configure parameters** — Edit namespace, threshold, quiet-for, padding, threads, skip-shorter per file or set defaults for all
3. **Set output directory** — Choose where processed segments will be saved
4. **Configure job concurrency** — Set how many files process in parallel (default: 2)
5. **Submit batch** — Click `[Process]` to start async background jobs
6. **Monitor progress** — Watch the Active Jobs table for real-time updates
7. **Close browser anytime** — Jobs continue running in the background; reopen the app to check status

## Features

- **Multi-file batching** — Process multiple files in a single batch
- **Per-file configuration** — Override parameters (threshold, quiet-for, padding, etc.) on a per-file basis
- **Global defaults** — Set default parameters that apply to all files
- **Async background processing** — Submit jobs and close the browser; jobs persist across sessions
- **Job persistence** — All job state stored in JSON files (survives app restarts)
- **Real-time monitoring** — Browser polls every 2 seconds for job updates
- **Cancel jobs** — Stop running jobs at any time
- **Error reporting** — Errors captured and displayed in the job status table

## Architecture

### Backend

- **Flask app** (`app.py`) — HTTP server with REST API endpoints
- **Job Manager** (`job_manager.py`) — Handles job queue, process spawning, concurrency limits, and state persistence
- **Job Persistence** (`.jobs/` directory) — JSON files store complete job state (files, parameters, progress, status)
- **Process Management** — Direct Python subprocess calls to `SilenceSplitter` (no CLI subprocess)
- **Startup Recovery** — On app start, checks for running processes and recovers stale jobs

### Frontend

- **Templates** (`templates/base.html`, `templates/index.html`) — Jinja2 HTML templates with vanilla JavaScript
- **Polling** — JavaScript `setInterval()` polls `/api/jobs` every 2 seconds for live updates
- **No build tools** — No Node.js, webpack, or other build complexity; server-rendered HTML

## API Endpoints

### List all jobs
```
GET /api/jobs
```
Returns JSON with all jobs (running and completed).

### Get job details
```
GET /api/jobs/<job_id>
```
Returns detailed status and progress for a single job.

### Create a new batch job
```
POST /api/jobs
Content-Type: application/json

{
  "files": [
    {
      "input": "/path/to/video.mp4",
      "namespace": "video",
      "output_dir": "/path/to/output",
      "parameters": {
        "threshold": "-10dB",
        "quiet_for": 3.5,
        "padding": 1.0,
        "threads": 2,
        "skip_shorter": 1.5
      }
    }
  ],
  "job_concurrency": 2,
  "dry_run": false
}
```
Creates a new job and returns the job ID.

### Cancel a job
```
DELETE /api/jobs/<job_id>
```
Stops a running job and marks it as cancelled.

## Job State

Jobs are stored as JSON files in `.jobs/` directory with a filename like `20260516_143022_abc123.json`.

Each job file contains:
- Job metadata (id, timestamps, status, pid)
- File list with per-file configuration and progress
- Global parameters (job_concurrency, dry_run)
- Per-file status (pending/running/completed/failed)
- Error messages if any step failed

Job files persist indefinitely for history and debugging.

## Configuration

All configuration is done through the web UI:

| Setting | Default | Description |
|---------|---------|-------------|
| Output Dir | `segments` | Root directory for output segments |
| Job Concurrency | 2 | Number of files to process in parallel (max 8) |
| Dry Run | unchecked | Preview changes without creating files |
| Threshold | -10dB | Silence detection sensitivity (per-file override available) |
| Quiet For | 3.5s | Minimum silence duration (per-file override available) |
| Padding | 1.0s | Buffer around silence boundaries (per-file override available) |
| Threads | 2 | Worker threads per job (per-file override available) |
| Skip Shorter | 1.5s | Minimum segment duration (per-file override available) |

## Tabs

- **Segment** — Implemented. Batch-process multiple video/audio files by splitting at silence boundaries.
- **Extract Audio** — Placeholder. Future feature for extracting audio from video files.
- **Transcribe** — Placeholder. Future feature for transcribing audio using Whisper.

## File Structure

```
app/
├── app.py                    Flask app with routes
├── job_manager.py            Job queue, process management, persistence
├── .jobs/                    Job state files (git-ignored)
│   ├── 20260516_143022_abc123.json
│   └── ...
└── templates/
    ├── base.html             Base template with tabs and polling
    └── index.html            Segment tab UI
```

## Error Handling

Common error scenarios are handled gracefully:

| Error | Handling |
|-------|----------|
| File not found | Job marked failed, error message displayed |
| Invalid output directory | Creation attempted; if fails, error shown |
| Invalid parameters | Validation on job creation; user notified |
| Process crash | Job marked failed, stderr captured |
| Missing permissions | Error reported with specific file path |
| Stale PID on startup | Job marked failed on recovery |

## Development Notes

- No external database — all state in JSON files
- No authentication — personal use only
- No fancy styling — simple, functional tables
- Minimal JavaScript — polling-based, no WebSockets
- Direct module imports — calls `SilenceSplitter.split()` directly, not via CLI

## Testing the App

**Test file addition:**
1. Click `[+ Add Files]` and select a few test video/audio files
2. Verify they appear in the input table with auto-generated namespaces

**Test parameter override:**
1. Click any parameter cell (e.g., Threshold) in the table
2. Type a new value and click elsewhere
3. Verify the change persists

**Test batch submission:**
1. Set job concurrency to 2
2. Add 3 files
3. Click `[Process]`
4. Verify jobs appear in Active Jobs table with status "Running" or "Pending"

**Test persistence:**
1. Start a batch job
2. Close the browser completely
3. Reopen the app (run `python web_ui_launch.py` again)
4. Verify job status is still visible and still running (if not yet complete)

**Test cancellation:**
1. Start a batch job
2. Click `[Cancel]` on a running job
3. Verify status changes to "Cancelled"

**Test error handling:**
1. Try to add a non-existent file path
2. Verify error message appears on job creation
3. Try an invalid output directory path
4. Verify appropriate error handling

## Troubleshooting

**App won't start:**
- Ensure Flask is installed: `pip install Flask`
- Check port 5000 is not in use: `lsof -i :5000`

**Jobs not appearing:**
- Check browser console for JavaScript errors (F12 → Console)
- Verify Flask server is running in terminal output
- Check `.jobs/` directory for job JSON files

**Process not running:**
- Check that input file path is correct and file exists
- Check output directory is writable
- Review job JSON file for error details

**Can't connect to localhost:5000:**
- Verify server is running: `python web_ui_launch.py` in terminal
- Try a different browser
- Check firewall isn't blocking port 5000
