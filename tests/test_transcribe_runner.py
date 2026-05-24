import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.audio_runner import AudioRunner
from app.transcribe_runner import TranscribeRunner
from link2video.auto.transcribe.models import Transcription


def _make_transcription():
    return Transcription(
        whisper_output={
            "text": "Hello world",
            "segments": [
                {
                    "id": 0, "seek": 0, "start": 0.0, "end": 1.0,
                    "text": "Hello",
                    "tokens": [1, 2],
                    "avg_logprob": -0.1,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.01,
                    "temperature": 0.0,
                },
                {
                    "id": 1, "seek": 0, "start": 1.0, "end": 2.0,
                    "text": " world",
                    "tokens": [3, 4],
                    "avg_logprob": -0.2,
                    "compression_ratio": 1.0,
                    "no_speech_prob": 0.01,
                    "temperature": 0.0,
                },
            ],
            "language": "en",
        },
        model="base",
        device="cpu",
        timestamp="2026-05-24T00:00:00Z",
        input_file="audio.mp3",
        language_requested="en",
    )


@pytest.fixture
def audio_runner():
    return AudioRunner()


@pytest.fixture
def runner(audio_runner):
    return TranscribeRunner(audio_runner)


def test_start_returns_12char_run_id(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video))
    assert isinstance(run_id, str)
    assert len(run_id) == 12


def test_get_returns_none_for_unknown_id(runner):
    assert runner.get("notarunid") is None


def test_run_completes_on_success(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={"yaml_path": str(tmp_path / "v.yaml")}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "completed"
    assert state["error"] is None


def test_run_fails_on_exception(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", side_effect=RuntimeError("whisper missing")):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    state = runner.get(run_id)
    assert state["status"] == "failed"
    assert "whisper missing" in state["error"]


def test_auto_extracts_audio_if_mp3_missing(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    # no v.mp3 exists

    transcription = _make_transcription()
    with patch.object(audio_runner, "_extract", return_value={}) as mock_extract, \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager"):
        MockProc.return_value.transcribe.return_value = transcription
        run_id = runner.start(str(video))
        time.sleep(0.3)

    mock_extract.assert_called_once_with(str(video))


def test_skips_extraction_if_mp3_exists(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    mp3 = tmp_path / "v.mp3"
    mp3.touch()

    transcription = _make_transcription()
    with patch.object(audio_runner, "_extract") as mock_extract, \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager"):
        MockProc.return_value.transcribe.return_value = transcription
        run_id = runner.start(str(video))
        time.sleep(0.3)

    mock_extract.assert_not_called()


def test_strips_whisper_noise_from_segments(runner, audio_runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    mp3 = tmp_path / "v.mp3"
    mp3.touch()

    transcription = _make_transcription()
    captured = {}

    def fake_update(video_path, section_key, data):
        captured.update(data)
        return "x.yaml"

    with patch.object(audio_runner, "_extract"), \
         patch("app.transcribe_runner.TranscribeProcessor") as MockProc, \
         patch("app.transcribe_runner.MetadataManager") as MockMgr:
        MockProc.return_value.transcribe.return_value = transcription
        MockMgr.return_value.update.side_effect = fake_update
        run_id = runner.start(str(video))
        time.sleep(0.3)

    assert captured["text"] == "Hello world"
    for seg in captured["segments"]:
        assert set(seg.keys()) == {"start", "end", "text"}


def test_clear_removes_entry(runner, tmp_path):
    video = tmp_path / "v.mp4"
    video.touch()
    with patch.object(runner, "_transcribe", return_value={}):
        run_id = runner.start(str(video))
        time.sleep(0.2)
    runner.clear(run_id)
    assert runner.get(run_id) is None
