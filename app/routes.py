"""Flask Blueprint containing all HTTP route handlers."""
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request

jobs_bp = Blueprint("jobs", __name__)


def _manager():
    return current_app.config["JOB_MANAGER"]


@jobs_bp.route("/")
def index():
    """Serve main page."""
    return render_template("base.html")


SCANNABLE_EXTENSIONS = {".mov", ".mp4"}


@jobs_bp.route("/api/scan", methods=["GET"])
def scan_folder():
    """Scan a folder (flat) for .mov/.mp4 files and return pre-filled file entries."""
    folder = request.args.get("path", "").strip()
    if not folder:
        return jsonify({"error": "path parameter is required"}), 400

    folder_path = Path(folder)
    if not folder_path.is_dir():
        return jsonify({"error": f"Not a directory: {folder}"}), 400

    files = []
    for entry in sorted(folder_path.iterdir()):
        if entry.is_file() and entry.suffix.lower() in SCANNABLE_EXTENSIONS:
            files.append({
                "input": str(entry),
                "namespace": entry.stem,
                "output_dir": str(folder_path / f"{entry.stem}-segments"),
                "parameters": {
                    "threshold": "-10dB",
                    "quiet_for": 3.5,
                    "padding": 1.0,
                    "threads": 2,
                    "skip_shorter": 1.5,
                },
            })

    return jsonify({"files": files, "count": len(files)})


@jobs_bp.route("/api/jobs", methods=["GET"])
def list_jobs():
    """Return list of all jobs."""
    return jsonify({"jobs": _manager().list_jobs()})


@jobs_bp.route("/api/jobs/<job_id>", methods=["GET"])
def get_job(job_id: str):
    """Return details for a specific job."""
    job = _manager().get_job(job_id)
    if not job:
        return jsonify({"error": "Job not found"}), 404
    return jsonify(job)


@jobs_bp.route("/api/jobs", methods=["POST"])
def create_job():
    """Create a new batch job."""
    data = request.get_json()
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400

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
    """Cancel and delete a job."""
    if _manager().cancel_job(job_id):
        return jsonify({"status": "deleted"}), 200
    return jsonify({"error": "Could not delete job"}), 400


@jobs_bp.route("/api/jobs/clear/all", methods=["DELETE"])
def clear_all_jobs():
    """Clear all job history."""
    _manager().clear_all_jobs()
    return jsonify({"status": "cleared"}), 200


# ── Download routes ────────────────────────────────────────────────────────────

def _download_runner():
    return current_app.config["DOWNLOAD_RUNNER"]


@jobs_bp.route("/api/download", methods=["POST"])
def start_download():
    """Start a background video download."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    url = (data.get("url") or "").strip()
    save_path = (data.get("save_path") or "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400
    if not save_path:
        return jsonify({"error": "save_path is required"}), 400
    tags = data.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    comments = data.get("comments") or ""
    run_id = _download_runner().start(url, save_path, tags, comments)
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/download/<run_id>", methods=["GET"])
def get_download(run_id: str):
    """Return status of a download run."""
    entry = _download_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/download/<run_id>", methods=["DELETE"])
def clear_download(run_id: str):
    """Remove a finished download entry."""
    _download_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200


# ── Audio routes ───────────────────────────────────────────────────────────────

def _audio_runner():
    return current_app.config["AUDIO_RUNNER"]


@jobs_bp.route("/api/audio", methods=["POST"])
def start_audio():
    """Start a background audio extraction."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    video_path = (data.get("video_path") or "").strip()
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    run_id = _audio_runner().start(video_path)
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/audio/<run_id>", methods=["GET"])
def get_audio(run_id: str):
    """Return status of an audio extraction run."""
    entry = _audio_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/audio/<run_id>", methods=["DELETE"])
def clear_audio(run_id: str):
    """Remove a finished audio extraction entry."""
    _audio_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200


# ── Transcribe routes ──────────────────────────────────────────────────────────

def _transcribe_runner():
    return current_app.config["TRANSCRIBE_RUNNER"]


@jobs_bp.route("/api/transcribe", methods=["POST"])
def start_transcribe():
    """Start a background transcription."""
    data = request.get_json(force=True, silent=True)
    if data is None:
        return jsonify({"error": "Request must be JSON"}), 400
    video_path = (data.get("video_path") or "").strip()
    if not video_path:
        return jsonify({"error": "video_path is required"}), 400
    model = (data.get("model") or "base").strip()
    language = (data.get("language") or "en").strip()
    device = (data.get("device") or "auto").strip()
    run_id = _transcribe_runner().start(video_path, model=model, language=language, device=device)
    return jsonify({"id": run_id}), 201


@jobs_bp.route("/api/transcribe/<run_id>", methods=["GET"])
def get_transcribe(run_id: str):
    """Return status of a transcription run."""
    entry = _transcribe_runner().get(run_id)
    if entry is None:
        return jsonify({"error": "Not found"}), 404
    return jsonify(entry)


@jobs_bp.route("/api/transcribe/<run_id>", methods=["DELETE"])
def clear_transcribe(run_id: str):
    """Remove a finished transcription entry."""
    _transcribe_runner().clear(run_id)
    return jsonify({"status": "cleared"}), 200
