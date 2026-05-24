import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.audio_runner import AudioRunner


@pytest.fixture
def runner():
    return AudioRunner()


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={"mp3_path": str(tmp_path / "v.mp3")}):
        run_id = runner.start(str(video))
    assert isinstance(run_id, str)
    assert len(run_id) == 12


def test_get_returns_none_for_unknown_id(runner):
    assert runner.get("notarunid") is None


def test_initial_state_is_pending_or_running(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={}):
        run_id = runner.start(str(video))
    state = runner.get(run_id)
    assert state["status"] in ("pending", "running", "completed")


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={"mp3_path": str(tmp_path / "v.mp3")}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["result"] == {"mp3_path": str(tmp_path / "v.mp3")}
    assert state["error"] is None


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", side_effect=RuntimeError("ffmpeg missing")):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "ffmpeg missing" in state["error"]
    assert state["result"] is None


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_extract", return_value={}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    runner.clear(run_id)
    assert runner.get(run_id) is None


def test_clear_nonexistent_run_is_safe(runner):
    runner.clear("does-not-exist")  # must not raise
