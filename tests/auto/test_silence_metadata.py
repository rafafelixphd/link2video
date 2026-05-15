"""Tests for MetadataGenerator class."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
import yaml

from link2video.auto.split.silent.metadata import MetadataGenerator


class TestMetadataGenerator:
    """Test suite for MetadataGenerator."""

    def test_frame_from_timestamp_with_mocked_fps(self):
        """Test frame calculation from timestamp with mocked FPS."""
        with patch.object(MetadataGenerator, 'get_fps', return_value=29.97):
            generator = MetadataGenerator('input.mp4')

            # Test case 1: timestamp=1.0 → frame=29
            frame = generator.frame_from_timestamp(1.0)
            assert frame == 29

            # Test case 2: timestamp=10.0 → frame=299
            frame = generator.frame_from_timestamp(10.0)
            assert frame == 299

    def test_write_metadata_creates_yaml(self):
        """Test that write_metadata creates a valid YAML file with correct content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "segment_001.yaml"
            original_file = Path(tmpdir) / "input.mp4"
            original_file.touch()

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator(str(original_file))
                generator.write_metadata(
                    segment_id=1,
                    original_file=str(original_file),
                    start=0.0,
                    end=31.2,
                    output_path=str(output_path)
                )

            # Verify file exists
            assert output_path.exists()

            # Verify YAML content
            with open(output_path, 'r') as f:
                content = yaml.safe_load(f)

            assert content['name'] == 'segment_001'
            assert content['original_file'] == str(original_file)
            assert content['fps'] == 30.0
            assert content['start'] == 0.0
            assert content['end'] == 31.2
            assert content['start_frame'] == 0
            assert content['end_frame'] == 936  # 31.2 * 30

    def test_frame_from_timestamp_with_decimal_values(self):
        """Test frame calculation with decimal timestamp values."""
        with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
            generator = MetadataGenerator('video.mp4')

            # Test with various decimal values
            assert generator.frame_from_timestamp(0.5) == 15
            assert generator.frame_from_timestamp(2.5) == 75
            assert generator.frame_from_timestamp(5.33) == 159

    def test_write_metadata_creates_directory_if_not_exists(self):
        """Test that write_metadata creates parent directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nested_path = Path(tmpdir) / "nested" / "dir" / "segment.yaml"
            original_file = Path(tmpdir) / "input.mp4"
            original_file.touch()

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator(str(original_file))
                generator.write_metadata(
                    segment_id=1,
                    original_file=str(original_file),
                    start=0.0,
                    end=10.0,
                    output_path=str(nested_path)
                )

            # Verify file exists and directory was created
            assert nested_path.exists()
            assert nested_path.parent.exists()

    def test_fps_caching(self):
        """Test that get_fps caches the result."""
        with patch('link2video.auto.split.silent.metadata.subprocess.run') as mock_run:
            mock_process = MagicMock()
            mock_process.stdout = json.dumps({
                'streams': [
                    {
                        'r_frame_rate': '30/1'
                    }
                ]
            })
            mock_run.return_value = mock_process

            generator = MetadataGenerator('input.mp4')

            # First call
            fps1 = generator.get_fps()
            # Second call should use cache
            fps2 = generator.get_fps()

            assert fps1 == fps2 == 30.0
            # Verify subprocess.run was called only once
            assert mock_run.call_count == 1

    def test_get_fps_parses_frame_rate_ratios(self):
        """Test that get_fps correctly parses frame rate ratios."""
        test_cases = [
            ('30/1', 30.0),
            ('30000/1001', 29.97002997002997),
            ('24/1', 24.0),
            ('60/1', 60.0),
        ]

        for frame_rate_str, expected_fps in test_cases:
            with patch('link2video.auto.split.silent.metadata.subprocess.run') as mock_run:
                mock_process = MagicMock()
                mock_process.stdout = json.dumps({
                    'streams': [
                        {
                            'r_frame_rate': frame_rate_str
                        }
                    ]
                })
                mock_run.return_value = mock_process

                generator = MetadataGenerator('input.mp4')
                fps = generator.get_fps()

                assert abs(fps - expected_fps) < 0.0001

    def test_write_metadata_rounds_values_correctly(self):
        """Test that write_metadata rounds fps, start, and end to 2 decimals."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "segment.yaml"
            original_file = Path(tmpdir) / "input.mp4"
            original_file.touch()

            with patch.object(MetadataGenerator, 'get_fps', return_value=29.97002997):
                generator = MetadataGenerator(str(original_file))
                generator.write_metadata(
                    segment_id=1,
                    original_file=str(original_file),
                    start=0.123456,
                    end=31.123456,
                    output_path=str(output_path)
                )

            with open(output_path, 'r') as f:
                content = yaml.safe_load(f)

            # Check rounded values
            assert content['fps'] == 29.97
            assert content['start'] == 0.12
            assert content['end'] == 31.12

    # Error case tests

    def test_write_metadata_validates_segment_id(self):
        """Test that write_metadata validates segment_id is positive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "segment.yaml"

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator('input.mp4')

                # Test negative segment_id
                with pytest.raises(ValueError, match="segment_id must be positive"):
                    generator.write_metadata(
                        segment_id=-1,
                        original_file='input.mp4',
                        start=0.0,
                        end=10.0,
                        output_path=str(output_path)
                    )

                # Test zero segment_id
                with pytest.raises(ValueError, match="segment_id must be positive"):
                    generator.write_metadata(
                        segment_id=0,
                        original_file='input.mp4',
                        start=0.0,
                        end=10.0,
                        output_path=str(output_path)
                    )

    def test_write_metadata_validates_original_file_exists(self):
        """Test that write_metadata validates original_file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "segment.yaml"

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator('input.mp4')

                with pytest.raises(FileNotFoundError, match="Original file not found"):
                    generator.write_metadata(
                        segment_id=1,
                        original_file='/nonexistent/file.mp4',
                        start=0.0,
                        end=10.0,
                        output_path=str(output_path)
                    )

    def test_write_metadata_validates_timestamps(self):
        """Test that write_metadata validates start and end times."""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "segment.yaml"

            # Create a temporary file to use as original_file
            original_file = Path(tmpdir) / "original.mp4"
            original_file.touch()

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator('input.mp4')

                # Test negative start
                with pytest.raises(ValueError, match="start time must be non-negative"):
                    generator.write_metadata(
                        segment_id=1,
                        original_file=str(original_file),
                        start=-1.0,
                        end=10.0,
                        output_path=str(output_path)
                    )

                # Test non-positive end
                with pytest.raises(ValueError, match="end time must be positive"):
                    generator.write_metadata(
                        segment_id=1,
                        original_file=str(original_file),
                        start=0.0,
                        end=0.0,
                        output_path=str(output_path)
                    )

                # Test start >= end
                with pytest.raises(ValueError, match="start .* must be less than end"):
                    generator.write_metadata(
                        segment_id=1,
                        original_file=str(original_file),
                        start=10.0,
                        end=5.0,
                        output_path=str(output_path)
                    )

    def test_frame_from_timestamp_rejects_negative(self):
        """Test that frame_from_timestamp rejects negative timestamps."""
        with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
            generator = MetadataGenerator('input.mp4')

            with pytest.raises(ValueError, match="timestamp must be non-negative"):
                generator.frame_from_timestamp(-1.0)

    def test_get_fps_handles_empty_streams(self):
        """Test that get_fps handles empty streams from ffprobe."""
        with patch('link2video.auto.split.silent.metadata.subprocess.run') as mock_run:
            mock_process = MagicMock()
            mock_process.stdout = json.dumps({'streams': []})
            mock_run.return_value = mock_process

            generator = MetadataGenerator('input.mp4')

            with pytest.raises(RuntimeError, match="No video streams found"):
                generator.get_fps()

    def test_get_fps_handles_zero_denominator(self):
        """Test that get_fps handles zero denominator in frame rate ratio."""
        with patch('link2video.auto.split.silent.metadata.subprocess.run') as mock_run:
            mock_process = MagicMock()
            mock_process.stdout = json.dumps({
                'streams': [
                    {
                        'r_frame_rate': '30/0'
                    }
                ]
            })
            mock_run.return_value = mock_process

            generator = MetadataGenerator('input.mp4')

            with pytest.raises(RuntimeError, match="Could not parse frame rate"):
                generator.get_fps()

    def test_write_metadata_handles_yaml_write_failure(self):
        """Test that write_metadata handles YAML write failures."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a temporary file to use as original_file
            original_file = Path(tmpdir) / "original.mp4"
            original_file.touch()

            output_path = Path(tmpdir) / "segment.yaml"

            with patch.object(MetadataGenerator, 'get_fps', return_value=30.0):
                generator = MetadataGenerator('input.mp4')

                # Mock open to raise IOError on write
                with patch('builtins.open', side_effect=IOError("Permission denied")):
                    with pytest.raises(IOError, match="Failed to write metadata"):
                        generator.write_metadata(
                            segment_id=1,
                            original_file=str(original_file),
                            start=0.0,
                            end=10.0,
                            output_path=str(output_path)
                        )
