from link2video.auto.caption.models import CaptionResult


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
