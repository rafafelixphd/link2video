"""
Multi-platform Video Downloader with Gooey GUI and CLI support.

Supports downloading videos from:
- Instagram (Reels, Posts)
- YouTube (Videos, Shorts)
- LinkedIn (Posts)

Features:
- Auto-platform detection
- Hash-based filename generation (YYYYMMDD_12hash.mp4)
- Metadata creation (YAML files with tags and comments)
- Enhanced GUI with tags and comments fields
- CLI mode for automated batch processing (--auto silence-split)
"""

import argparse
import os
import sys
from gooey import Gooey, GooeyParser

from .platform_detector import detect_platform
from .config import get_default_download_path
from .auto.split.silent import SilenceSplitter
from .auto.extract_audio import ExtractAudioProcessor
from .auto.transcribe import TranscribeProcessor


def normalize_threshold(value: str) -> str:
    """
    Normalize threshold to always end with 'dB'.

    Examples:
        "-10" → "-10dB"
        "-10dB" → "-10dB"
        "-10DB" → "-10dB"
    """
    value = value.strip()
    if not value.upper().endswith("DB"):
        value += "dB"
    else:
        # Ensure lowercase 'dB'
        if value.endswith("DB"):
            value = value[:-2] + "dB"
    return value


def _handle_silence_split(args):
    """
    Handle the --auto silence-split CLI subcommand.

    Args:
        args: Parsed command-line arguments containing input file, output settings, and processing parameters.

    Raises:
        SystemExit: On file not found or processing errors.
    """
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    splitter = SilenceSplitter()

    try:
        segments = splitter.split(
            input_file=args.input,
            output_dir=args.output_dir,
            namespace=args.namespace,
            threshold=args.threshold,
            quiet_for=args.quiet_for,
            padding=args.padding,
            threads=args.threads,
            skip_shorter=args.skip_shorter,
            dry_run=args.dry_run,
        )

        if args.dry_run:
            print("\n(Preview mode — no files were created)")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _handle_extract_audio(args):
    """
    Handle the --auto extract-audio CLI subcommand.

    Args:
        args: Parsed command-line arguments for audio extraction.

    Raises:
        SystemExit: On file not found or processing errors.
    """
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    processor = ExtractAudioProcessor()

    try:
        result = processor.extract(
            input_file=args.input,
            output_dir=args.output_dir,
            namespace=args.namespace,
            format=args.format,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            print(f"\nAudio extraction complete!")
            print(f"  Audio file: {result.audio_path}")
            print(f"  Metadata: {result.metadata_path}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


def _handle_transcribe(args):
    """
    Handle the --auto transcribe CLI subcommand.

    Args:
        args: Parsed command-line arguments for transcription.

    Raises:
        SystemExit: On file not found or processing errors.
    """
    if not os.path.isfile(args.input):
        print(f"Error: file not found: {args.input}", file=sys.stderr)
        sys.exit(1)

    processor = TranscribeProcessor()

    try:
        result = processor.transcribe(
            audio_file=args.input,
            output_dir=args.output_dir,
            namespace=args.namespace,
            model=args.model,
            language=args.language,
            device=args.device,
            dry_run=args.dry_run,
        )

        if not args.dry_run:
            output_path = os.path.join(args.output_dir, args.namespace, f"{args.namespace}.json")
            print(f"\nTranscription complete!")
            print(f"  Output: {output_path}")

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


@Gooey(
    program_name="Multi-Platform Video Downloader",
    default_size=(700, 600),
    richtext_controls=True,
    navigation='TABBED',
    body_bg_color='#2b2b2b',
    footer_bg_color='#2b2b2b',
    sidebar_bg_color='#1e1e1e',
    richtext_bg_color='#1e1e1e',
    optional_cols=2,
    progress_regex=r"^Progress: (\d+)%$",
    progress_expr="x / 100"
)
def _run_gui_downloader(args):
    """
    Run the GUI downloader.

    Provides a user-friendly interface for downloading videos from multiple platforms.
    Automatically detects the platform based on URL and routes to the appropriate downloader.
    Creates metadata files alongside downloaded videos.
    """
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


def main():
    """
    Main entry point supporting both GUI and CLI modes.

    For CLI usage:
        link2video --auto silence-split <input> --namespace <name> [--output-dir <dir>] [options]

    For GUI mode (default):
        link2video <url> <save_path> [--tags <tags>] [--comments <notes>]
    """
    # Check for CLI mode first (--auto flag in sys.argv)
    if "--auto" in sys.argv:
        # CLI mode: parse and route to CLI handler
        # Remove --auto from argv and rebuild argv for argparse
        auto_index = sys.argv.index("--auto")
        cli_argv = [sys.argv[0]] + sys.argv[auto_index + 1:]

        parser = argparse.ArgumentParser(
            description="link2video - Video processing suite",
            prog=sys.argv[0]
        )
        subparsers = parser.add_subparsers(
            dest="auto_command",
            help="Processing command",
            required=True
        )

        # silence-split subcommand with all parameters
        silence_split = subparsers.add_parser(
            "segment",
            help="Split video at silent gaps"
        )
        silence_split.add_argument(
            "input",
            help="Input video file path"
        )
        silence_split.add_argument(
            "--namespace",
            required=True,
            help="Output folder and filename prefix (e.g., 'my-project' creates {output_dir}/my-project/segment_001.mp4)"
        )
        silence_split.add_argument(
            "--output-dir",
            default="segments",
            help="Root directory for output segments (default: segments)"
        )
        silence_split.add_argument(
            "--threshold",
            type=normalize_threshold,
            default="-10dB",
            help="Silence detection threshold in dB. Lower (more negative) values detect quieter silences. Increase this to ignore background noise (default: -35dB)"
        )
        silence_split.add_argument(
            "--quiet-for",
            type=float,
            default=3.5,
            help="Minimum duration of silence in seconds to count as a split point. Increase this to ignore brief pauses within sentences like breathing or hesitation (default: 3.5)"
        )
        silence_split.add_argument(
            "--padding",
            type=float,
            default=1.0,
            help="Buffer zone in seconds on both sides of detected silence boundaries. Prevents cutting too close to the end of one sentence or the beginning of the next. Increase if speech is being cut off at segment edges (default: 1.0)"
        )
        silence_split.add_argument(
            "--threads",
            type=int,
            default=2,
            help="Number of parallel worker threads for cutting segments. Increase on high-performance systems for faster processing (default: 2)"
        )
        silence_split.add_argument(
            "--skip-shorter",
            type=float,
            default=1.5,
            help="Minimum segment duration in seconds. Shorter segments are automatically discarded. Increase this to ensure meaningful content in each segment (default: 3.0)"
        )
        silence_split.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview planned segments without cutting or creating files. Useful for tuning parameters before committing"
        )

        # extract-audio subcommand
        extract_audio = subparsers.add_parser(
            "extract-audio",
            help="Extract audio from video or audio file"
        )
        extract_audio.add_argument(
            "input",
            help="Input video or audio file path"
        )
        extract_audio.add_argument(
            "--namespace",
            required=True,
            help="Output filename prefix"
        )
        extract_audio.add_argument(
            "--output-dir",
            default="segments",
            help="Root directory for output (default: segments)"
        )
        extract_audio.add_argument(
            "--format",
            choices=["wav", "mp3"],
            default="wav",
            help="Output audio format (default: wav)"
        )
        extract_audio.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without creating files"
        )

        # transcribe subcommand
        transcribe = subparsers.add_parser(
            "transcribe",
            help="Transcribe audio using Whisper"
        )
        transcribe.add_argument(
            "input",
            help="Input audio file path"
        )
        transcribe.add_argument(
            "--namespace",
            required=True,
            help="Output filename prefix"
        )
        transcribe.add_argument(
            "--output-dir",
            default="segments",
            help="Root directory for output (default: segments)"
        )
        transcribe.add_argument(
            "--model",
            choices=["tiny", "base", "small", "medium", "large"],
            default="base",
            help="Whisper model to use (default: base)"
        )
        transcribe.add_argument(
            "--language",
            choices=["en", "ja", "pt"],
            default="en",
            help="Language code (default: en)"
        )
        transcribe.add_argument(
            "--device",
            choices=["auto", "cpu", "cuda", "mps"],
            default="auto",
            help="Device to use for processing (default: auto)"
        )
        transcribe.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview without processing"
        )

        args = parser.parse_args(cli_argv[1:])

        # Route to handler
        if args.auto_command == "segment":
            _handle_silence_split(args)
        elif args.auto_command == "extract-audio":
            _handle_extract_audio(args)
        elif args.auto_command == "transcribe":
            _handle_transcribe(args)
        else:
            parser.print_help()
            sys.exit(1)

        return

    # GUI mode: default behavior for backward compatibility
    gui_parser = GooeyParser(
        description="Download videos from Instagram, YouTube, and LinkedIn with automatic platform detection and metadata creation"
    )

    # Get default download path from config
    try:
        default_path = get_default_download_path()
    except Exception:
        default_path = os.path.expanduser("~/Movies")

    # Main download arguments
    gui_parser.add_argument(
        'url',
        metavar='Video URL',
        help="Enter the URL of the video (Instagram, YouTube, or LinkedIn)",
        widget='TextField',
        gooey_options={
            'columns': 2,
            'full_width': True
        }
    )

    gui_parser.add_argument(
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

    gui_parser.add_argument(
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

    gui_parser.add_argument(
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

    args = gui_parser.parse_args()
    _run_gui_downloader(args)


if __name__ == "__main__":
    main()


