import os
import yt_dlp
from .base import BaseDownloader


class YouTubeLinkedInDownloader(BaseDownloader):
    """
    YouTube and LinkedIn video downloader that inherits from BaseDownloader.

    Uses the yt-dlp library to download videos from YouTube and LinkedIn,
    and handles filename generation and metadata through the parent BaseDownloader class.
    """

    def __init__(self):
        """Initialize the YouTube/LinkedIn downloader with yt-dlp configuration."""
        self.ydl_opts = {
            'format': 'best[ext=mp4]',
            'quiet': True,
            'no_warnings': True,
        }

    def _download_video(self, url: str, filepath: str) -> None:
        """
        Download a YouTube or LinkedIn video and save it to the specified filepath.

        This method:
        1. Validates that the URL is a YouTube or LinkedIn URL
        2. Configures yt-dlp with the target filepath
        3. Downloads the video in best quality MP4 format
        4. Handles yt-dlp specific errors and converts them to RuntimeError

        Args:
            url (str): The URL of the video (YouTube or LinkedIn)
            filepath (str): The target filepath where the video should be saved

        Raises:
            RuntimeError: If URL is invalid, not a YouTube/LinkedIn URL, or download fails
        """
        # Validate that this is a YouTube or LinkedIn URL
        url_lower = url.lower()
        is_youtube = 'youtube.com' in url_lower or 'youtu.be' in url_lower
        is_linkedin = 'linkedin.com' in url_lower

        if not is_youtube and not is_linkedin:
            raise RuntimeError("URL must be a YouTube or LinkedIn URL")

        try:
            # Configure yt-dlp options with the output filepath
            # Use the full path and let yt-dlp enforce the extension
            ydl_opts = self.ydl_opts.copy()
            ydl_opts['outtmpl'] = filepath

            # Download the video using yt-dlp
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if not info:
                    raise RuntimeError("Failed to extract video information")

            # Handle case where yt-dlp saves without extension
            # Check if file exists with the expected filepath
            if not os.path.exists(filepath):
                # Try to find the file without extension
                base_path = filepath.rsplit('.', 1)[0] if filepath.endswith('.mp4') else filepath
                if os.path.exists(base_path):
                    os.rename(base_path, filepath)
                else:
                    raise RuntimeError(f"Downloaded file not found at {filepath} or {base_path}")

        except yt_dlp.utils.DownloadError as e:
            raise RuntimeError(f"Download failed: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error downloading video: {str(e)}")
