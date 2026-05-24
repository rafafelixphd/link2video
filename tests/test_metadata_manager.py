from datetime import date
from pathlib import Path

import pytest
import yaml

from link2video.metadata_manager import MetadataManager


@pytest.fixture
def tmp_video(tmp_path):
    video = tmp_path / "my_video.mp4"
    video.touch()
    return str(video)


def test_creates_yaml_alongside_video(tmp_video):
    mgr = MetadataManager()
    yaml_path = mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    assert Path(yaml_path) == Path(tmp_video).with_suffix(".yaml")
    assert Path(yaml_path).exists()


def test_returns_yaml_path_as_string(tmp_video):
    mgr = MetadataManager()
    result = mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    assert isinstance(result, str)


def test_populates_generic_fields_on_first_write(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["name"] == "my_video"
    assert data["original_file"] == tmp_video
    assert data["date"] == str(date.today())


def test_writes_section_key_block(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com", "tags": ["a", "b"]})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["link2video/download"] == {"url": "http://x.com", "tags": ["a", "b"]}


def test_accumulates_multiple_sections(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    mgr.update(tmp_video, "link2video/auto/extract", {"format": "mp3", "duration": 10.0})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert "link2video/download" in data
    assert "link2video/auto/extract" in data


def test_overwrites_existing_section(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://old.com"})
    mgr.update(tmp_video, "link2video/download", {"url": "http://new.com"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["link2video/download"]["url"] == "http://new.com"


def test_generic_fields_not_overwritten_on_second_write(tmp_video):
    mgr = MetadataManager()
    mgr.update(tmp_video, "link2video/download", {"url": "http://x.com"})
    mgr.update(tmp_video, "link2video/auto/extract", {"format": "mp3"})
    data = yaml.safe_load(Path(tmp_video).with_suffix(".yaml").read_text())
    assert data["name"] == "my_video"
    assert data["original_file"] == tmp_video
