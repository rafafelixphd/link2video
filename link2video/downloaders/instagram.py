import instaloader
import os
import shutil
import tempfile
from .base import BaseDownloader


class InstagramDownloader(BaseDownloader):
    """
    Instagram Reel downloader that inherits from BaseDownloader.

    Uses the instaloader library to download Instagram Reels and handles
    filename generation and metadata through the parent BaseDownloader class.
    """

    def __init__(self):
        """Initialize the Instagram downloader with an instaloader context."""
        self.loader = instaloader.Instaloader()

    def _download_video(self, url: str, filepath: str) -> None:
        """
        Download an Instagram Reel video and save it to the specified filepath.

        This method:
        1. Extracts the shortcode from the Instagram URL
        2. Retrieves the post using instaloader
        3. Validates that the post is a video
        4. Downloads the post to a temporary directory
        5. Finds and moves the MP4 file to the target filepath
        6. Cleans up temporary files

        Args:
            url (str): The Instagram URL (e.g., https://www.instagram.com/reel/ABC123/)
            filepath (str): The target filepath where the video should be saved

        Raises:
            RuntimeError: If URL is invalid, post is not a video, or download fails
            ValueError: If the shortcode cannot be extracted from the URL
        """
        # Validate that this is an Instagram URL
        if 'instagram.com' not in url.lower():
            raise RuntimeError("URL must be an Instagram URL")

        temp_dir = None
        try:
            # Extract shortcode from URL
            # URLs like: https://www.instagram.com/reel/ABC123/ or
            # https://www.instagram.com/reel/ABC123
            parts = url.rstrip('/').split('/')
            if len(parts) < 2:
                raise ValueError("Invalid Instagram URL format")

            shortcode = parts[-1]
            if not shortcode or not shortcode.replace('-', '').replace('_', '').isalnum():
                raise ValueError(f"Invalid shortcode extracted from URL: {shortcode}")

            # Get the post from Instagram
            post = instaloader.Post.from_shortcode(self.loader.context, shortcode)

            # Validate that it's a video
            if not post.is_video:
                raise RuntimeError("The provided URL does not point to a video")

            # Create a temporary directory for download
            temp_dir = tempfile.mkdtemp()

            # Download the post to the temporary directory
            self.loader.download_post(post, target=temp_dir)

            # Find the MP4 file in the downloaded content
            mp4_file = None
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.mp4'):
                        mp4_file = os.path.join(root, file)
                        break
                if mp4_file:
                    break

            if not mp4_file:
                raise RuntimeError("No MP4 file found in downloaded content")

            # Move the MP4 file to the target filepath
            shutil.move(mp4_file, filepath)

        except instaloader.InstaloaderException as e:
            raise RuntimeError(f"Instagram download failed: {str(e)}")
        except ValueError as e:
            raise RuntimeError(f"Invalid URL: {str(e)}")
        except Exception as e:
            raise RuntimeError(f"Error downloading Instagram video: {str(e)}")
        finally:
            # Clean up temporary directory
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                except Exception:
                    pass
