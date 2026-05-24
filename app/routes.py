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
