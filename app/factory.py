"""Flask application factory."""
from flask import Flask, request

from job_manager import JobManager
from routes import jobs_bp


def create_app(jobs_dir: str = "app/.jobs") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")

    job_manager = JobManager(jobs_dir=jobs_dir)
    job_manager.recover()
    app.config["JOB_MANAGER"] = job_manager

    app.register_blueprint(jobs_bp)

    @app.before_request
    def tick():
        if request.endpoint != "static":
            app.config["JOB_MANAGER"].process_queue()

    return app
