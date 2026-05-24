"""Flask application factory."""
from flask import Flask, request

from audio_runner import AudioRunner
from download_runner import DownloadRunner
from job_manager import JobManager
from routes import jobs_bp
from transcribe_runner import TranscribeRunner


def create_app(jobs_dir: str = "app/.jobs") -> Flask:
    """Create and configure the Flask application."""
    app = Flask(__name__, template_folder="templates")

    job_manager = JobManager(jobs_dir=jobs_dir)
    job_manager.recover()
    app.config["JOB_MANAGER"] = job_manager

    app.config["DOWNLOAD_RUNNER"] = DownloadRunner()

    audio_runner = AudioRunner()
    app.config["AUDIO_RUNNER"] = audio_runner
    app.config["TRANSCRIBE_RUNNER"] = TranscribeRunner(audio_runner)

    app.register_blueprint(jobs_bp)

    @app.before_request
    def tick():
        if request.endpoint != "static":
            app.config["JOB_MANAGER"].process_queue()

    return app
