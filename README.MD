# link2video

A multi-platform video downloader with GUI support for Instagram, YouTube, and LinkedIn.

## Features

- **Multi-Platform Support**: Download videos from Instagram, YouTube, and LinkedIn
- **Auto-Platform Detection**: Automatically detects the video platform from URL
- **Hash-Based Naming**: Videos are saved with format `YYYYMMDD_12hash.mp4` for automatic organization
- **Metadata Creation**: Automatically generates YAML metadata files alongside videos with tags and comments
- **Graphical Interface**: User-friendly Gooey GUI for easy interaction

## Installation

Install the package in development mode:

```bash
pip install -e .
```

## Usage

Launch the GUI from the command line:

```bash
link2video
```

This will open the graphical interface where you can:

1. Enter a video URL (Instagram, YouTube, or LinkedIn)
2. Select the directory to save the video
3. Add optional tags for categorization
4. Add optional comments or notes
5. Click download

## Supported Platforms

- **Instagram**: Reels, Posts, Videos
- **YouTube**: Videos, Shorts
- **LinkedIn**: Posts

## Metadata Files

For each downloaded video, a `metadata.yaml` file is automatically created in a `metadata/` subdirectory containing:

- Original URL
- Download date
- Tags
- Comments/Notes

## Requirements

All dependencies are listed in `requirements.txt`:

- `instaloader` - Instagram downloader
- `yt-dlp` - YouTube/LinkedIn downloader
- `Gooey` - GUI framework
- `PyYAML` - Metadata handling
- `colored` - Colored terminal output

## License

This project is licensed under the Apache License 2.0 - see the LICENSE file for details.
