import json
import pytest
from unittest.mock import MagicMock, patch
from app.factory import create_app


@pytest.fixture
def client(tmp_path):
    app = create_app(jobs_dir=str(tmp_path))
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def test_get_root(client):
    resp = client.get("/")
    assert resp.status_code == 200


def test_list_jobs_empty(client):
    resp = client.get("/api/jobs")
    assert resp.status_code == 200
    assert resp.get_json() == {"jobs": []}


def test_create_job_missing_files(client):
    resp = client.post("/api/jobs", json={"output_dir": "/out"})
    assert resp.status_code == 400


def test_create_job_missing_output_dir(client):
    resp = client.post("/api/jobs", json={"files": [{"input": "/f.mp4", "namespace": "f"}]})
    assert resp.status_code == 400


def test_create_job_success(client):
    resp = client.post("/api/jobs", json={
        "files": [{"input": "/f.mp4", "namespace": "f", "output_dir": "/out",
                   "parameters": {"threshold": "-10dB", "quiet_for": 3.5, "padding": 1.0, "threads": 2, "skip_shorter": 1.5}}],
        "output_dir": "/out",
        "job_concurrency": 1,
        "dry_run": False,
    })
    assert resp.status_code == 201
    assert "id" in resp.get_json()


def test_delete_nonexistent_job(client):
    resp = client.delete("/api/jobs/nonexistent_id")
    assert resp.status_code == 400


def test_clear_all_jobs(client):
    resp = client.delete("/api/jobs/clear/all")
    assert resp.status_code == 200


def test_scan_folder_no_path(client):
    resp = client.get("/api/scan")
    assert resp.status_code == 400


def test_scan_folder_not_a_dir(client):
    resp = client.get("/api/scan?path=/nonexistent/path/xyz")
    assert resp.status_code == 400


def test_scan_folder_finds_files(client, tmp_path):
    (tmp_path / "clip.mp4").touch()
    (tmp_path / "interview.mov").touch()
    (tmp_path / "notes.txt").touch()   # should be ignored

    resp = client.get(f"/api/scan?path={tmp_path}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 2
    names = {f["namespace"] for f in data["files"]}
    assert names == {"clip", "interview"}
    # output_dir follows {stem}-segments convention
    for f in data["files"]:
        assert f["output_dir"].endswith(f["namespace"] + "-segments")


def test_scan_folder_empty(client, tmp_path):
    resp = client.get(f"/api/scan?path={tmp_path}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["count"] == 0
    assert data["files"] == []


# ── Download route tests ──────────────────────────────────────────────────────

def test_start_download_no_body(client):
    resp = client.post("/api/download")
    assert resp.status_code == 400


def test_start_download_missing_url(client):
    resp = client.post("/api/download", json={"save_path": "/tmp/out"})
    assert resp.status_code == 400
    assert "url" in resp.get_json()["error"]


def test_start_download_missing_save_path(client):
    resp = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc"})
    assert resp.status_code == 400
    assert "save_path" in resp.get_json()["error"]


def test_start_download_returns_id(client):
    from unittest.mock import patch
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, "/out/video.mp4")
        resp = client.post("/api/download", json={
            "url": "https://youtube.com/watch?v=abc",
            "save_path": "/tmp/out",
        })
    assert resp.status_code == 201
    data = resp.get_json()
    assert "id" in data
    assert isinstance(data["id"], str)


def test_get_download_not_found(client):
    resp = client.get("/api/download/nonexistent_run_id")
    assert resp.status_code == 404


def test_get_download_status(client):
    from unittest.mock import patch
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, "/out/video.mp4")
        post_resp = client.post("/api/download", json={
            "url": "https://youtube.com/watch?v=abc",
            "save_path": "/tmp/out",
        })
    run_id = post_resp.get_json()["id"]
    resp = client.get(f"/api/download/{run_id}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "status" in data
    assert data["status"] in ("pending", "running", "completed", "failed")
    assert "result" in data
    assert "error" in data


def test_clear_download(client):
    from unittest.mock import patch
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, "/out/video.mp4")
        post_resp = client.post("/api/download", json={
            "url": "https://youtube.com/watch?v=abc",
            "save_path": "/tmp/out",
        })
    run_id = post_resp.get_json()["id"]
    resp = client.delete(f"/api/download/{run_id}")
    assert resp.status_code == 200
    assert resp.get_json() == {"status": "cleared"}
    # confirm it's gone
    assert client.get(f"/api/download/{run_id}").status_code == 404


@pytest.fixture
def client_with_runners(tmp_path):
    app = create_app(jobs_dir=str(tmp_path))
    app.config["TESTING"] = True

    mock_audio = MagicMock()
    mock_audio.start.return_value = "abc123456789"
    mock_audio.get.return_value = {"status": "completed", "result": {"mp3_path": "/v/v.mp3"}, "error": None}
    app.config["AUDIO_RUNNER"] = mock_audio

    mock_transcribe = MagicMock()
    mock_transcribe.start.return_value = "def987654321"
    mock_transcribe.get.return_value = {"status": "completed", "result": {"yaml_path": "/v/v.yaml"}, "error": None}
    app.config["TRANSCRIBE_RUNNER"] = mock_transcribe

    with app.test_client() as c:
        c.app = app
        yield c


# Audio routes
def test_post_audio_missing_video_path(client_with_runners):
    resp = client_with_runners.post("/api/audio", json={})
    assert resp.status_code == 400
    assert "video_path" in resp.get_json()["error"]


def test_post_audio_no_body(client_with_runners):
    resp = client_with_runners.post("/api/audio")
    assert resp.status_code == 400


def test_post_audio_success(client_with_runners):
    resp = client_with_runners.post("/api/audio", json={"video_path": "/videos/v.mp4"})
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "abc123456789"


def test_get_audio_found(client_with_runners):
    resp = client_with_runners.get("/api/audio/abc123456789")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "completed"


def test_get_audio_not_found(client_with_runners):
    client_with_runners.app.config["AUDIO_RUNNER"].get.return_value = None
    resp = client_with_runners.get("/api/audio/notexist")
    assert resp.status_code == 404


def test_delete_audio(client_with_runners):
    resp = client_with_runners.delete("/api/audio/abc123456789")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "cleared"


# Transcribe routes
def test_post_transcribe_no_body(client_with_runners):
    resp = client_with_runners.post("/api/transcribe")
    assert resp.status_code == 400


def test_post_transcribe_missing_video_path(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={})
    assert resp.status_code == 400


def test_post_transcribe_success(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={
        "video_path": "/videos/v.mp4",
        "model": "small",
        "language": "pt",
        "device": "cpu",
    })
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "def987654321"


def test_post_transcribe_defaults(client_with_runners):
    resp = client_with_runners.post("/api/transcribe", json={"video_path": "/videos/v.mp4"})
    assert resp.status_code == 201
    client_with_runners.app.config["TRANSCRIBE_RUNNER"].start.assert_called_with(
        "/videos/v.mp4", model="base", language="en", device="auto"
    )


def test_get_transcribe_found(client_with_runners):
    resp = client_with_runners.get("/api/transcribe/def987654321")
    assert resp.status_code == 200


def test_get_transcribe_not_found(client_with_runners):
    client_with_runners.app.config["TRANSCRIBE_RUNNER"].get.return_value = None
    resp = client_with_runners.get("/api/transcribe/notexist")
    assert resp.status_code == 404


def test_delete_transcribe(client_with_runners):
    resp = client_with_runners.delete("/api/transcribe/def987654321")
    assert resp.status_code == 200


# ── Ollama / YAML-info / Caption route tests ──────────────────────────────────

def test_get_ollama_models_success(client):
    mock_model_a = MagicMock()
    mock_model_a.model = "llava"
    mock_model_b = MagicMock()
    mock_model_b.model = "moondream"
    mock_list_resp = MagicMock()
    mock_list_resp.models = [mock_model_a, mock_model_b]
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.list.return_value = mock_list_resp
        resp = client.get("/api/ollama/models")
    assert resp.status_code == 200
    assert resp.get_json() == {"models": ["llava", "moondream"]}


def test_get_ollama_models_unreachable(client):
    with patch("ollama.Client") as mock_client_cls:
        mock_client_cls.return_value.list.side_effect = Exception("connection refused")
        resp = client.get("/api/ollama/models")
    assert resp.status_code == 502


def test_get_yaml_info_no_yaml(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    resp = client.get(f"/api/yaml-info?path={video}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["exists"] is False
    assert data["sections"] == []


def test_get_yaml_info_with_yaml(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    yaml_path = tmp_path / "v.yaml"
    yaml_path.write_text(
        "link2video/auto/transcribe:\n  text: hello\n"
        "link2video/download:\n  comments: nice\n"
    )
    resp = client.get(f"/api/yaml-info?path={video}")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["exists"] is True
    assert "transcription" in data["sections"]
    assert "comments" in data["sections"]
    assert data["comments"] == "nice"


def test_post_caption_missing_video_path(client):
    resp = client.post("/api/caption", json={})
    assert resp.status_code == 400


def test_post_caption_success(client, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    runner_mock = MagicMock()
    runner_mock.start.return_value = "abc123def456"
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.post("/api/caption", json={
        "video_path": str(video),
        "interval_seconds": 1.0,
        "sequence_length": 3,
        "model": "llava",
        "additional_query": "",
        "context_sections": ["transcription"],
    })
    assert resp.status_code == 201
    assert resp.get_json()["id"] == "abc123def456"


def test_get_caption_not_found(client):
    runner_mock = MagicMock()
    runner_mock.get.return_value = None
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.get("/api/caption/doesnotexist")
    assert resp.status_code == 404


def test_delete_caption_run(client):
    runner_mock = MagicMock()
    client.application.config["CAPTION_RUNNER"] = runner_mock
    resp = client.delete("/api/caption/abc123")
    assert resp.status_code == 200
