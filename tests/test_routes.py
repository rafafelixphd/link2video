import json
import pytest
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
