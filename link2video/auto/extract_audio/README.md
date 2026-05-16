# Extract Audio Module

## What This Module Does

The extract-audio module takes a video file (or audio file) and extracts just the audio portion. It saves the audio as a separate file and creates a detailed metadata file that analyzes the audio's loudness levels frame-by-frame.

This is useful when you want to:
- Get just the audio from a video file for transcription or analysis
- Analyze audio quality and loudness characteristics
- Prepare audio for speech-to-text services
- Build an audio library with loudness metrics

## Quick Start

The simplest way to extract audio from a video:

```bash
link2video --auto extract-audio myrecording.mp4 --namespace my-audio
```

This will create:
- `segments/my-audio/my-audio.wav` — the extracted audio file
- `segments/my-audio/my-audio.yaml` — metadata with audio analysis

## Full Command Syntax

```bash
link2video --auto extract-audio <input_file> \
  --namespace <name> \
  [--output-dir <dir>] \
  [--format wav|mp3] \
  [--dry-run]
```

## Parameters Explained

### Required Parameters

**`<input_file>`** (positional argument)
- The path to your video or audio file
- Can be: MP4, MOV, AVI, WebM, WAV, MP3, etc.
- Examples: `./video.mp4`, `/home/user/recording.mov`, `../videos/interview.mkv`

**`--namespace <name>`** (required)
- A label for your output files (no spaces or special characters, use hyphens)
- The output files will be named: `{namespace}.wav` and `{namespace}.yaml`
- Examples: `--namespace my-video`, `--namespace lecture-001`, `--namespace podcast-episode-5`

### Optional Parameters

**`--output-dir <dir>`** (default: `segments`)
- Where to save the extracted files
- A folder named after your namespace will be created inside this directory
- Examples: 
  - `--output-dir ./audio_files` → creates `./audio_files/my-audio/`
  - `--output-dir /data/extracted` → creates `/data/extracted/my-audio/`

**`--format wav|mp3`** (default: `wav`)
- Choose the audio file format
- `wav` — Lossless, higher quality, larger file size (recommended for transcription)
- `mp3` — Compressed, smaller file size, slightly lower quality
- Use `--format wav` for transcription (better accuracy)
- Use `--format mp3` if you want to save disk space
- Example: `--format mp3` to save as MP3 instead of WAV

**`--dry-run`** (optional flag)
- Preview what will happen without actually creating files
- Useful to test your parameters before committing
- Example: Add `--dry-run` to see the output paths without extraction

## Output Files

### Audio File
`{namespace}.wav` (or `.mp3` if you used `--format mp3`)

The extracted audio in your chosen format, ready to use with transcription services or other audio processing tools.

### Metadata File
`{namespace}.yaml`

A YAML file containing detailed analysis of the audio. Here's an example:

```yaml
audio:
  format: wav
  duration: 120.5          # Length of audio in seconds
  sample_rate: 44100       # Samples per second (Hz)
  channels: 2              # Number of audio channels (mono=1, stereo=2)

audio_levels:
  min_db: -40.5           # Quietest point in the audio
  max_db: -5.2            # Loudest point in the audio
  mean_db: -20.3          # Average loudness
  peak_db: -3.1           # Peak loudness (99th percentile)
  db_array: [-22.5, -21.8, -20.9, -19.5, ..., -18.2]  # Frame-by-frame loudness values
```

**What the numbers mean:**
- Higher DB values = louder audio
- -60dB = very quiet, -20dB = medium, -3dB = very loud
- The `db_array` has one value per audio frame, allowing detailed loudness analysis
- Use this data to identify quiet sections, peaks, or overall audio quality

## Common Use Cases

### Case 1: Extract Audio for Transcription

```bash
link2video --auto extract-audio lecture.mp4 \
  --namespace lecture-01 \
  --format wav
```

This creates a WAV file (better for speech recognition) with loudness analysis to check recording quality.

### Case 2: Save Space with MP3

```bash
link2video --auto extract-audio podcast.mov \
  --namespace podcast-episode-42 \
  --format mp3 \
  --output-dir ./podcasts
```

Saves as MP3 to use less disk space while keeping good quality.

### Case 3: Preview First, Then Extract

```bash
# First, preview without extracting
link2video --auto extract-audio recording.mkv \
  --namespace test-extract \
  --dry-run

# If the preview looks good, run without --dry-run
link2video --auto extract-audio recording.mkv \
  --namespace test-extract
```

### Case 4: Batch Processing Multiple Videos

```bash
# Extract audio from multiple files with different namespaces
link2video --auto extract-audio video1.mp4 --namespace part-1
link2video --auto extract-audio video2.mp4 --namespace part-2
link2video --auto extract-audio video3.mp4 --namespace part-3
```

All go to the default `segments/` directory organized by namespace.

## Understanding the Metadata

The `db_array` in the YAML file is an array of loudness measurements, one for each frame of audio. This lets you:

- **Check recording quality:** Look at `min_db` and `max_db` to see the range
- **Identify quiet sections:** Find where `db_array` values drop significantly
- **Identify loud peaks:** Find where values spike
- **Analyze patterns:** See if the recording gets quieter or louder over time
- **Build a loudness library:** Keep metadata files for future analysis

Example: If you're preparing audio for transcription, you might check that `mean_db` is in a reasonable range (e.g., -25 to -15) to ensure good recording quality.

## Troubleshooting

### Error: "FFmpeg not found"
**Solution:** Install FFmpeg on your system
- macOS: `brew install ffmpeg`
- Ubuntu/Debian: `apt-get install ffmpeg`
- Windows: Download from https://ffmpeg.org/download.html

### Error: "Input file not found"
**Solution:** Check that your file path is correct
- Use absolute paths to be safe: `/home/user/videos/myfile.mp4`
- Check the file actually exists with: `ls -la yourfile.mp4`

### Error: "Failed to load audio with librosa"
**Solution:** The audio format might be corrupted or unusual
- Try converting to a standard format first using FFmpeg
- Check the file is actually a valid audio/video file

### The extracted audio sounds distorted or wrong
**Solution:** 
- Try a different input file to test
- Check your original video file isn't corrupted
- Check FFmpeg installation is working: `ffmpeg -version`

### Output files are huge (WAV format)
**Solution:** Use MP3 format instead
- Use `--format mp3` to save space
- MP3 is ~10x smaller but still good quality for most uses

### Need to analyze the metadata later?

The YAML files are human-readable and can be parsed by other tools:

```bash
# View the metadata
cat segments/my-audio/my-audio.yaml

# Use it with Python
python3 << 'EOF'
import yaml
with open('segments/my-audio/my-audio.yaml') as f:
    metadata = yaml.safe_load(f)
    print(f"Duration: {metadata['audio']['duration']} seconds")
    print(f"Average loudness: {metadata['audio_levels']['mean_db']} dB")
EOF
```

## Tips for Best Results

1. **For transcription:** Always use `--format wav` for best speech-to-text accuracy
2. **Check quality first:** Look at the metadata to confirm your original recording has good levels
3. **Organize by namespace:** Use descriptive namespace names like `interview-john-2026-05-16` to stay organized
4. **Keep metadata:** The YAML files are small and contain useful analysis—save them alongside your audio
5. **Batch organize:** Use different `--namespace` values and optionally different `--output-dir` values to organize large projects

## What's Next?

After extracting audio, you typically want to:
- **Transcribe it:** Use `link2video --auto transcribe` to convert speech to text
- **Analyze it:** Use the metadata to understand recording quality
- **Process it:** Use external audio tools with the extracted WAV/MP3 file
