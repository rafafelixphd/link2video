#!/usr/bin/env python3
"""Worker script for batch processing. Called as subprocess by job_manager."""
import sys
import json
from pathlib import Path

from link2video.auto.split.silent import SilenceSplitter


def main():
    """Process a single file using SilenceSplitter."""
    if len(sys.argv) < 2:
        print("Usage: worker.py <json_config>", file=sys.stderr)
        sys.exit(1)

    # Load config from JSON file
    config_file = sys.argv[1]
    with open(config_file) as f:
        config = json.load(f)

    input_file = config["input_file"]
    output_dir = config["output_dir"]
    namespace = config["namespace"]
    params = config["parameters"]
    dry_run = config.get("dry_run", False)

    # Validate input file exists
    if not Path(input_file).exists():
        print(f"ERROR: File not found: {input_file}", file=sys.stderr)
        sys.exit(1)

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    try:
        # Call SilenceSplitter directly
        splitter = SilenceSplitter()
        segments = splitter.split(
            input_file=input_file,
            output_dir=output_dir,
            namespace=namespace,
            threshold=params.get("threshold", "-10dB"),
            quiet_for=params.get("quiet_for", 3.5),
            padding=params.get("padding", 1.0),
            threads=params.get("threads", 2),
            skip_shorter=params.get("skip_shorter", 3.0),
            dry_run=dry_run,
        )
        print(f"SUCCESS: Created {len(segments)} segments")
        sys.exit(0)
    except Exception as e:
        print(f"ERROR: {str(e)}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
