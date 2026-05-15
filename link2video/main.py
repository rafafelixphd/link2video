"""
Multi-platform Video Downloader with Gooey GUI.

Supports downloading videos from:
- Instagram (Reels, Posts)
- YouTube (Videos, Shorts)
- LinkedIn (Posts)

Features:
- Auto-platform detection
- Hash-based filename generation (YYYYMMDD_12hash.mp4)
- Metadata creation (YAML files with tags and comments)
- Enhanced GUI with tags and comments fields
"""

import os
from gooey import Gooey, GooeyParser

from .platform_detector import detect_platform
from .config import get_default_download_path


@Gooey(
    program_name="Multi-Platform Video Downloader",
    default_size=(700, 600),
    richtext_controls=True,
    navigation='TABBED',
    body_bg_color='#2b2b2b',
    footer_bg_color='#2b2b2b',
    sidebar_bg_color='#1e1e1e',
    richtext_bg_color='#1e1e1e'
)
def main():
    """
    Main GUI entry point using Gooey.

    Provides a user-friendly interface for downloading videos from multiple platforms.
    Automatically detects the platform based on URL and routes to the appropriate downloader.
    Creates metadata files alongside downloaded videos.
    """
    parser = GooeyParser(
        description="Download videos from Instagram, YouTube, and LinkedIn with automatic platform detection and metadata creation"
    )

    # Get default download path from config
    try:
        default_path = get_default_download_path()
    except Exception:
        default_path = os.path.expanduser("~/Movies")

    # Main download arguments
    parser.add_argument(
        'url',
        metavar='Video URL',
        help="Enter the URL of the video (Instagram, YouTube, or LinkedIn)",
        widget='TextField',
        gooey_options={
            'columns': 2,
            'full_width': True
        }
    )

    parser.add_argument(
        'save_path',
        metavar='Save Directory',
        help="Select the directory to save the video",
        widget='DirChooser',
        gooey_options={
            'columns': 2,
            'default': default_path
        },
        default=default_path
    )

    parser.add_argument(
        '--tags',
        metavar='Tags (optional)',
        help="Comma-separated tags for categorization (e.g., tutorial, funny, important)",
        default='',
        widget='TextField',
        gooey_options={
            'columns': 2,
            'full_width': True
        }
    )

    parser.add_argument(
        '--comments',
        metavar='Comments/Notes (optional)',
        help="Additional notes or comments about this video",
        default='',
        widget='Textarea',
        gooey_options={
            'columns': 2,
            'full_width': True,
            'height': 100
        }
    )

    args = parser.parse_args()

    # Validate inputs
    if not args.url or not args.url.strip():
        print("Error: URL cannot be empty")
        return

    if not args.save_path or not args.save_path.strip():
        print("Error: Save directory cannot be empty")
        return

    # Parse tags from comma-separated string
    tags = []
    if args.tags and args.tags.strip():
        tags = [tag.strip() for tag in args.tags.split(',') if tag.strip()]

    # Get comments
    comments = args.comments.strip() if args.comments else ""

    try:
        # Detect platform and get appropriate downloader
        downloader = detect_platform(args.url)

        # Perform download with metadata
        success, result = downloader.download(
            url=args.url,
            save_path=args.save_path,
            tags=tags,
            comments=comments
        )

        if success:
            # Extract just the filename for cleaner output
            filepath = result
            filename = os.path.basename(filepath)
            print(f"✓ Downloaded Successfully: {filename}")
            print(f"  Location: {filepath}")
            if tags:
                print(f"  Tags: {', '.join(tags)}")
            if comments:
                print(f"  Notes: {comments}")
            print(f"\nMetadata file created: {os.path.dirname(filepath)}/metadata/")
        else:
            print(f"Error: {result}")

    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()


