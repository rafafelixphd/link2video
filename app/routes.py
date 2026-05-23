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
