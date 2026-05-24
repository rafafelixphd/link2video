import subprocess
from unittest.mock import MagicMock, patch

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


def test_call_ollama_returns_text():
    processor = CaptionProcessor(ollama_url="http://fake")
    fake_response = MagicMock()
    fake_response.__getitem__ = lambda self, key: "Frame 1: A desk.\nFrame 2: A chair." if key == "response" else None
    with patch.object(processor._client, "generate", return_value={"response": "Frame 1: A desk.\nFrame 2: A chair."}) as mock_gen:
        text = processor._call_ollama(
            model="llava",
            prompt="describe",
            images=["aGVsbG8=", "d29ybGQ="],
        )
    assert text == "Frame 1: A desk.\nFrame 2: A chair."
    mock_gen.assert_called_once_with(
        model="llava",
        prompt="describe",
        images=["aGVsbG8=", "d29ybGQ="],
    )


def test_call_ollama_no_images():
    processor = CaptionProcessor(ollama_url="http://fake")
    with patch.object(processor._client, "generate", return_value={"response": "Summary."}) as mock_gen:
        text = processor._call_ollama(model="llava", prompt="summarize")
    call_kwargs = mock_gen.call_args[1]
    assert "images" not in call_kwargs


def test_parse_frame_descriptions_extracts_one_per_frame():
    processor = CaptionProcessor(ollama_url="http://fake")
    text = "Frame 1: A person sits.\nFrame 2: They gesture.\nFrame 3: Close-up of screen."
    result = processor._parse_frame_descriptions(text, expected_count=3)
    assert result == [
        "A person sits.",
        "They gesture.",
        "Close-up of screen.",
    ]


def test_parse_frame_descriptions_fills_parse_errors():
    processor = CaptionProcessor(ollama_url="http://fake")
    text = "Frame 1: Hello.\nFrame 2: World."
    result = processor._parse_frame_descriptions(text, expected_count=3)
    assert len(result) == 3
    assert result[2] == "[parse error]"
