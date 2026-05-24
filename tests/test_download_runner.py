import time
from unittest.mock import patch
from app.download_runner import DownloadRunner


def test_start_returns_run_id():
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, "/out/video.mp4")
        run_id = runner.start("https://youtube.com/watch?v=abc", "/tmp/out", [], "")
    assert isinstance(run_id, str)
    assert len(run_id) == 12


def test_get_returns_none_for_unknown_run():
    runner = DownloadRunner()
    assert runner.get("nonexistent") is None


def test_get_initial_state():
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, "/out/video.mp4")
        run_id = runner.start("https://youtube.com/watch?v=abc", "/tmp/out", [], "")
    state = runner.get(run_id)
    assert state is not None
    assert state["status"] in ("pending", "running", "completed")
    assert "result" in state
    assert "error" in state


def test_successful_download(tmp_path):
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, str(tmp_path / "video.mp4"))
        run_id = runner.start("https://youtube.com/watch?v=abc", str(tmp_path), [], "")
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["result"] == str(tmp_path / "video.mp4")
    assert state["error"] is None


def test_failed_download_from_downloader(tmp_path):
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (False, "Download failed: 403 Forbidden")
        run_id = runner.start("https://youtube.com/watch?v=abc", str(tmp_path), [], "")
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert state["error"] == "Download failed: 403 Forbidden"
    assert state["result"] is None


def test_failed_download_from_exception(tmp_path):
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.side_effect = RuntimeError("network error")
        run_id = runner.start("https://youtube.com/watch?v=abc", str(tmp_path), [], "")
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "network error" in state["error"]


def test_clear_removes_run(tmp_path):
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, str(tmp_path / "video.mp4"))
        run_id = runner.start("https://youtube.com/watch?v=abc", str(tmp_path), [], "")
        time.sleep(0.2)
    runner.clear(run_id)
    assert runner.get(run_id) is None


def test_clear_nonexistent_run_is_safe():
    runner = DownloadRunner()
    runner.clear("does-not-exist")  # must not raise


def test_tags_and_comments_passed_to_downloader(tmp_path):
    runner = DownloadRunner()
    with patch("app.download_runner.detect_platform") as mock:
        mock.return_value.download.return_value = (True, str(tmp_path / "video.mp4"))
        run_id = runner.start(
            "https://youtube.com/watch?v=abc",
            str(tmp_path),
            ["tutorial", "python"],
            "my note",
        )
        time.sleep(0.2)
    mock.return_value.download.assert_called_once_with(
        "https://youtube.com/watch?v=abc",
        str(tmp_path),
        tags=["tutorial", "python"],
        comments="my note",
    )
