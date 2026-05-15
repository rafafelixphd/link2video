import queue
import threading
from unittest.mock import patch, MagicMock
import pytest

from link2video.auto.split.silent.detector import SilenceDetector, SENTINEL


class TestSilenceDetector:
    """Tests for the SilenceDetector class."""

    def test_detector_parses_silence_pairs(self):
        """
        Test that SilenceDetector correctly parses silence pairs and applies padding.

        Input: Two silences [0.5-3.2, 10.1-12.5] with padding=1.0
        Expected: [(1.5, 2.2), (11.1, 11.5)]
        """
        # Mock ffmpeg stderr output with silence_start and silence_end lines
        ffmpeg_output = [
            b"[silencedetect @ 0x...] silence_start: 0.5\n",
            b"[silencedetect @ 0x...] silence_end: 3.2\n",
            b"[silencedetect @ 0x...] silence_start: 10.1\n",
            b"[silencedetect @ 0x...] silence_end: 12.5\n",
        ]

        # Create detector with padding=1.0
        detector = SilenceDetector(
            input_file="test.mp3",
            noise="-10dB",
            duration=3.5,
            padding=1.0
        )

        # Mock subprocess.Popen to return fake stderr output
        mock_process = MagicMock()
        mock_process.stderr = iter(ffmpeg_output)

        with patch("subprocess.Popen", return_value=mock_process):
            q = queue.Queue()
            detector.detect(q)

        # Verify queue contains correct pairs
        result_pairs = []
        while True:
            item = q.get()
            if item is SENTINEL:
                break
            result_pairs.append(item)

        # Expected: [(1.5, 2.2), (11.1, 11.5)]
        # cut_before = silence_start + padding
        # cut_after = silence_end - padding
        assert len(result_pairs) == 2
        assert result_pairs[0] == (1.5, 2.2)  # 0.5+1.0=1.5, 3.2-1.0=2.2
        assert result_pairs[1] == (11.1, 11.5)  # 10.1+1.0=11.1, 12.5-1.0=11.5

    def test_detector_applies_padding(self):
        """
        Test padding logic with different padding value.

        Input: Single silence [10.0-15.0] with padding=0.5
        Expected: (10.5, 14.5)
        """
        ffmpeg_output = [
            b"[silencedetect @ 0x...] silence_start: 10.0\n",
            b"[silencedetect @ 0x...] silence_end: 15.0\n",
        ]

        detector = SilenceDetector(
            input_file="test.mp3",
            noise="-10dB",
            duration=3.5,
            padding=0.5
        )

        mock_process = MagicMock()
        mock_process.stderr = iter(ffmpeg_output)

        with patch("subprocess.Popen", return_value=mock_process):
            q = queue.Queue()
            detector.detect(q)

        result_pairs = []
        while True:
            item = q.get()
            if item is SENTINEL:
                break
            result_pairs.append(item)

        assert len(result_pairs) == 1
        assert result_pairs[0] == (10.5, 14.5)  # 10.0+0.5=10.5, 15.0-0.5=14.5

    def test_spawn_detector_thread(self):
        """Test that spawn_detector_thread starts a daemon thread."""
        ffmpeg_output = [
            b"[silencedetect @ 0x...] silence_start: 0.5\n",
            b"[silencedetect @ 0x...] silence_end: 3.2\n",
        ]

        detector = SilenceDetector(
            input_file="test.mp3",
            noise="-10dB",
            duration=3.5,
            padding=1.0
        )

        mock_process = MagicMock()
        mock_process.stderr = iter(ffmpeg_output)

        with patch("subprocess.Popen", return_value=mock_process):
            q = queue.Queue()
            thread = detector.spawn_detector_thread(q)

            # Verify it's a daemon thread
            assert thread.daemon is True

            # Wait for thread to complete
            thread.join(timeout=5)
            assert not thread.is_alive()

            # Verify queue has the expected pairs and SENTINEL
            result_pairs = []
            while True:
                item = q.get(timeout=1)
                if item is SENTINEL:
                    break
                result_pairs.append(item)

            assert len(result_pairs) == 1
            assert result_pairs[0] == (1.5, 2.2)
