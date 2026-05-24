import yaml
from pathlib import Path
from datetime import date
from typing import Dict, List, Optional


def create_metadata(
    url: str,
    tags: Optional[List[str]] = None,
    comments: str = ""
) -> Dict:
    """
    Create a metadata dictionary for a downloaded video.

    Args:
        url (str): The URL of the video source
        tags (Optional[List[str]]): List of tags for categorization (default: None)
        comments (str): Additional comments or notes about the video (default: "")

    Returns:
        Dict: Dictionary containing url, date, tags, and comments

    Raises:
        ValueError: If url is empty or None
    """
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    metadata = {
        'url': url,
        'date': str(date.today()),
        'tags': tags or [],
        'comments': comments
    }

    return metadata


def save_metadata(
    filename: str,
    url: str,
    tags=None,
    comments: str = ""
) -> str:
    """
    Save metadata for a video as a YAML file.

    The metadata is saved alongside the video file in the same directory.
    The metadata filename is derived from the video filename without its extension.

    Args:
        filename (str): The path to the video file
        url (str): The URL of the video source
        tags (Optional[List[str]]): List of tags (default: None)
        comments (str): Additional comments (default: "")

    Returns:
        str: The path to the saved metadata file

    Raises:
        ValueError: If url or filename is empty
    """
    if not filename:
        raise ValueError("Filename cannot be empty")
    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    from link2video.metadata_manager import MetadataManager
    mgr = MetadataManager()
    return mgr.update(filename, "link2video/download", {
        "url": url,
        "tags": tags or [],
        "comments": comments,
    })
