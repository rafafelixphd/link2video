import hashlib
import os
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import date
from typing import Tuple, Optional, List
from ..metadata import save_metadata


class BaseDownloader(ABC):
    """
    Abstract base class for video downloaders.

    Handles common functionality like filename generation, directory creation,
    and metadata integration. Subclasses must implement the _download_video() method.
    """

    def generate_filename(self, url: str, extension: str = 'mp4') -> str:
        """
        Generate a filename for a downloaded video.

        Format: YYYYMMDD_12hash.ext
        - YYYYMMDD: Current date
        - 12hash: First 12 characters of SHA256 hash of the URL
        - ext: File extension (default: mp4)

        Args:
            url (str): The video URL to hash
            extension (str): File extension without the dot (default: 'mp4')

        Returns:
            str: Generated filename in format YYYYMMDD_12hash.ext

        Raises:
            ValueError: If url is empty or None
        """
        if not url or not url.strip():
            raise ValueError("URL cannot be empty")

        # Generate hash of URL
        url_hash = hashlib.sha256(url.encode()).hexdigest()[:12]

        # Get current date in YYYYMMDD format
        current_date = date.today().strftime('%Y%m%d')

        # Build filename
        filename = f"{current_date}_{url_hash}.{extension}"

        return filename

    def download(
        self,
        url: str,
        save_path: str,
        tags: Optional[List[str]] = None,
        comments: str = ""
    ) -> Tuple[bool, str]:
        """
        Download a video and save metadata.

        This method:
        1. Creates the save directory if it doesn't exist
        2. Generates a filename
        3. Calls _download_video() to perform the actual download
        4. Saves metadata alongside the video

        Args:
            url (str): The URL of the video to download
            save_path (str): Directory where to save the video
            tags (Optional[List[str]]): Tags for categorization (default: None)
            comments (str): Additional comments about the video (default: "")

        Returns:
            Tuple[bool, str]: (success, filepath_or_error_message)
                - If successful: (True, full_path_to_video_file)
                - If failed: (False, error_message)

        Raises:
            No exceptions are raised. All errors are returned in the tuple.
        """
        try:
            # Validate inputs
            if not url or not url.strip():
                return (False, "URL cannot be empty")

            if not save_path or not save_path.strip():
                return (False, "Save path cannot be empty")

            # Create save directory if it doesn't exist
            try:
                save_dir = Path(save_path)
                save_dir.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                return (False, f"Failed to create directory {save_path}: {str(e)}")

            # Generate filename
            filename = self.generate_filename(url)
            filepath = os.path.join(save_path, filename)

            # Call abstract method to perform the actual download
            try:
                self._download_video(url, filepath)
            except NotImplementedError:
                return (False, "Subclass must implement _download_video() method")
            except Exception as e:
                return (False, f"Download failed: {str(e)}")

            # Check if file was created
            if not os.path.exists(filepath):
                return (False, f"File was not created at {filepath}")

            # Save metadata
            try:
                save_metadata(filepath, url, tags=tags, comments=comments)
            except Exception as e:
                # If metadata save fails, still consider download successful
                # but log the metadata error
                pass

            return (True, filepath)

        except Exception as e:
            return (False, f"Unexpected error: {str(e)}")

    @abstractmethod
    def _download_video(self, url: str, filepath: str) -> None:
        """
        Download the video and save it to the specified filepath.

        This method must be implemented by subclasses.

        Args:
            url (str): The URL of the video to download
            filepath (str): The path where the video should be saved

        Raises:
            Subclasses should raise appropriate exceptions on failure.
            The download() method will catch these exceptions.
        """
        pass
