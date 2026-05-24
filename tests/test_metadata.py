import yaml
from pathlib import Path
from link2video.metadata import save_metadata


def test_save_metadata_saves_yaml_alongside_video(tmp_path):
    video_file = tmp_path / "20260524_abc123def456.mp4"
    video_file.touch()
    result = save_metadata(str(video_file), "https://youtube.com/watch?v=abc")
    expected = tmp_path / "20260524_abc123def456.yaml"
    assert Path(result) == expected
    assert expected.exists()


def test_save_metadata_yaml_content(tmp_path):
    video_file = tmp_path / "video.mp4"
    video_file.touch()
    save_metadata(str(video_file), "https://youtube.com/watch?v=abc",
                  tags=["tutorial", "python"], comments="test note")
    yaml_file = tmp_path / "video.yaml"
    content = yaml.safe_load(yaml_file.read_text())
    assert content["link2video/download"]["url"] == "https://youtube.com/watch?v=abc"
    assert content["link2video/download"]["tags"] == ["tutorial", "python"]
    assert content["link2video/download"]["comments"] == "test note"
    assert "name" in content
    assert "original_file" in content
    assert "date" in content


def test_save_metadata_no_metadata_subfolder_created(tmp_path):
    video_file = tmp_path / "video.mp4"
    video_file.touch()
    save_metadata(str(video_file), "https://youtube.com/watch?v=abc")
    assert not (tmp_path / "metadata").exists()
