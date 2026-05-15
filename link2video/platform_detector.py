"""
Platform detection utility for routing URLs to appropriate downloader instances.

This module provides functionality to detect which platform a URL belongs to
and returns the appropriate downloader instance for that platform.
"""

from .downloaders.instagram import InstagramDownloader
from .downloaders.youtube import YouTubeLinkedInDownloader
from .downloaders.base import BaseDownloader


def detect_platform(url: str) -> BaseDownloader:
    """
    Detect the platform of a given URL and return the appropriate downloader instance.

    This function analyzes a URL to determine which platform it belongs to and returns
    an instance of the corresponding downloader. Detection is case-insensitive to handle
    URLs with varying cases.

    Platform detection logic:
    - Instagram: URLs containing 'instagram.com' → InstagramDownloader
    - YouTube: URLs containing 'youtube.com' or 'youtu.be' → YouTubeLinkedInDownloader
    - LinkedIn: URLs containing 'linkedin.com' → YouTubeLinkedInDownloader
    - Unknown: All other URLs → YouTubeLinkedInDownloader (default)

    Args:
        url (str): The URL to analyze (e.g., 'https://www.instagram.com/reel/ABC123/')

    Returns:
        BaseDownloader: An instance of the appropriate downloader:
            - InstagramDownloader for Instagram URLs
            - YouTubeLinkedInDownloader for YouTube, LinkedIn, or unknown URLs

    Examples:
        >>> downloader = detect_platform('https://www.instagram.com/reel/ABC123/')
        >>> isinstance(downloader, InstagramDownloader)
        True

        >>> downloader = detect_platform('https://www.youtube.com/watch?v=ABC123')
        >>> isinstance(downloader, YouTubeLinkedInDownloader)
        True

        >>> downloader = detect_platform('https://www.linkedin.com/posts/ABC123')
        >>> isinstance(downloader, YouTubeLinkedInDownloader)
        True

        >>> downloader = detect_platform('https://unknown.com/video')
        >>> isinstance(downloader, YouTubeLinkedInDownloader)
        True
    """
    # Convert URL to lowercase for case-insensitive matching
    url_lower = url.lower()

    # Check for Instagram
    if 'instagram.com' in url_lower:
        return InstagramDownloader()

    # Check for YouTube (both youtube.com and youtu.be short URLs)
    if 'youtube.com' in url_lower or 'youtu.be' in url_lower:
        return YouTubeLinkedInDownloader()

    # Check for LinkedIn
    if 'linkedin.com' in url_lower:
        return YouTubeLinkedInDownloader()

    # Default to YouTubeLinkedInDownloader for unknown platforms
    return YouTubeLinkedInDownloader()
