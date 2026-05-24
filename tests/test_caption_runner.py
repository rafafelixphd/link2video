import time
from unittest.mock import patch

import pytest

from app.caption_runner import CaptionRunner
from link2video.auto.caption.models import CaptionResult


@pytest.fixture
def runner():
    return CaptionRunner(ollama_url="http://fake")


def _fake_result():
    return CaptionResult(
        global_summary="Summary.",
        model="llava",
        interval_seconds=1.0,
        sequence_length=3,
        length_seconds=5.0,
        units=[{"timestamp": 0.0, "description": "A desk."}],
        context_used=[],
    )


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
    assert isinstance(run_id, str) and len(run_id) == 12


def test_get_returns_none_for_unknown(runner):
    assert runner.get("notexist") is None


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    expected = {"yaml_path": str(tmp_path / "v.yaml")}
    with patch.object(runner, "_caption", return_value=expected):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["result"] == expected


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", side_effect=RuntimeError("Ollama down")):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "Ollama down" in state["error"]


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_caption", return_value={}):
        run_id = runner.start(str(video), interval_seconds=1.0, sequence_length=3,
                              model="llava", additional_query="", context_sections=[])
        time.sleep(0.3)
    runner.clear(run_id)
    assert runner.get(run_id) is None


def test_clear_nonexistent_is_safe(runner):
    runner.clear("nope")
