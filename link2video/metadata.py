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
    tags: Optional[List[str]] = None,
    comments: str = ""
) -> str:
    """
    Save metadata for a video as a YAML file.

    The metadata is saved in a 'metadata/' subdirectory relative to the provided filename.
    The metadata filename is derived from the video filename without its extension.

    Args:
        filename (str): The path to the video file (used to determine save location)
        url (str): The URL of the video source
        tags (Optional[List[str]]): List of tags for categorization (default: None)
        comments (str): Additional comments or notes about the video (default: "")

    Returns:
        str: The path to the saved metadata file

    Raises:
        ValueError: If url is empty or None, or if filename is empty
        PermissionError: If the metadata directory cannot be created or written to
    """
    if not filename:
        raise ValueError("Filename cannot be empty")

    if not url or not url.strip():
        raise ValueError("URL cannot be empty")

    # Get the directory containing the video file
    video_path = Path(filename)
    video_dir = video_path.parent
    video_basename = video_path.stem  # Filename without extension

    # Create metadata directory
    metadata_dir = video_dir / "metadata"

    try:
        metadata_dir.mkdir(exist_ok=True)
    except PermissionError as e:
        raise PermissionError(f"Permission denied creating metadata directory: {metadata_dir}") from e
    except OSError as e:
        raise PermissionError(f"Error creating metadata directory: {metadata_dir}") from e

    # Create the metadata dictionary
    metadata = create_metadata(url, tags, comments)

    # Build the metadata file path
    metadata_file = metadata_dir / f"{video_basename}.yaml"

    # Write metadata to YAML file
    try:
        with open(metadata_file, 'w') as file:
            yaml.safe_dump(metadata, file, default_flow_style=False)
    except PermissionError as e:
        raise PermissionError(f"Permission denied writing metadata file: {metadata_file}") from e
    except OSError as e:
        raise PermissionError(f"Error writing metadata file: {metadata_file}") from e

    return str(metadata_file)
