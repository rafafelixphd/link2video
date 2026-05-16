"""
Flask web application for batch segment processing.

Routes:
- GET  /                   Serve index.html
- POST /api/jobs           Create new batch job
- GET  /api/jobs           List all jobs
- GET  /api/jobs/<id>      Get job details
- DELETE /api/jobs/<id>    Cancel job
"""
import json
import os
from flask import Flask, render_template, request, jsonify
from pathlib import Path
from .job_manager import JobManager


def create_app(jobs_dir: str = "app/.jobs") -> Flask:
    """Create and configure Flask application."""
    app = Flask(__name__, template_folder="templates")
    job_manager = JobManager(jobs_dir=jobs_dir)

    # Recover running jobs on startup
    with app.app_context():
        for job_file in Path(jobs_dir).glob("*.json"):
            try:
                with open(job_file) as f:
                    job = json.load(f)
                if job["status"] == "running" and job.get("pid"):
                    # Check if process still alive
                    try:
                        os.kill(job["pid"], 0)
                    except ProcessLookupError:
                        # Process dead
                        job["status"] = "failed"
                        job["error"] = "Process terminated unexpectedly"
                        job_manager._persist_job(job["id"], job)
            except (json.JSONDecodeError, KeyError):
                pass

    @app.route("/")
    def index():
        """Serve main page."""
        return render_template("base.html")

    @app.route("/api/jobs", methods=["GET"])
    def list_jobs():
        """Return list of all jobs."""
        jobs = job_manager.list_jobs()
        return jsonify({"jobs": jobs})

    @app.route("/api/jobs/<job_id>", methods=["GET"])
    def get_job(job_id: str):
        """Return details for a specific job."""
        job = job_manager.get_job(job_id)
        if not job:
            return jsonify({"error": "Job not found"}), 404
        return jsonify(job)

    @app.route("/api/jobs", methods=["POST"])
    def create_job():
        """Create new batch job."""
        data = request.get_json()

        # Validate input
        if not data.get("files"):
            return jsonify({"error": "No files provided"}), 400
        if not data.get("output_dir"):
            return jsonify({"error": "Output directory required"}), 400

        # Validate file paths
        for f in data["files"]:
            if not f.get("input"):
                return jsonify({"error": "File path required for all files"}), 400
            if not f.get("namespace"):
                return jsonify({"error": "Namespace required for all files"}), 400

        files = data["files"]
        global_params = {
            "job_concurrency": min(data.get("job_concurrency", 2), 8),  # Cap at 8
            "dry_run": data.get("dry_run", False),
        }

        job_id = job_manager.create_job(files, global_params)
        return jsonify({"id": job_id}), 201

    @app.route("/api/jobs/<job_id>", methods=["DELETE"])
    def cancel_job(job_id: str):
        """Cancel a running job."""
        success = job_manager.cancel_job(job_id)
        if success:
            return jsonify({"status": "cancelled"}), 200
        else:
            return jsonify({"error": "Could not cancel job"}), 400

    @app.before_request
    def process_queue():
        """Process job queue on each request."""
        job_manager.process_queue()

    return app
