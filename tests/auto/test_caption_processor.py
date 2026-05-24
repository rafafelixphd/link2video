import subprocess
from unittest.mock import patch, MagicMock

from link2video.auto.caption.models import CaptionResult
from link2video.auto.caption.processor import CaptionProcessor


def test_caption_result_to_dict():
    result = CaptionResult(
        global_summary="A person talks.",
        model="llava",
        interval_seconds=1.0,
        sequence_length=3,
        length_seconds=5.0,
        units=[{"timestamp": 0.0, "description": "Frame one."}],
        context_used=["transcription"],
    )
    d = result.to_dict()
    assert d["global"] == "A person talks."
    assert d["model"] == "llava"
    assert d["interval_seconds"] == 1.0
    assert d["sequence_length"] == 3
    assert d["length"] == "5.0s"
    assert d["units"] == [{"timestamp": 0.0, "description": "Frame one."}]
    assert d["context_used"] == ["transcription"]


def test_get_video_duration(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(stdout="42.5\n", returncode=0)
        duration = processor._get_video_duration(str(tmp_path / "v.mp4"))
    assert duration == 42.5


def test_extract_frames_calls_ffmpeg(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    video = tmp_path / "v.mp4"
    video.touch()
    out_dir = tmp_path / "frames"
    out_dir.mkdir()
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        processor._extract_frames(str(video), str(out_dir), interval_seconds=2.0)
    call_args = mock_run.call_args[0][0]
    assert "ffmpeg" in call_args
    assert "fps=1/2.0" in " ".join(call_args)


def test_encode_frame_returns_base64_string(tmp_path):
    processor = CaptionProcessor(ollama_url="http://fake")
    img = tmp_path / "frame_0000.jpg"
    img.write_bytes(b"\xff\xd8\xff")  # minimal JPEG header
    result = processor._encode_frame(str(img))
    import base64
    assert base64.b64decode(result) == b"\xff\xd8\xff"
