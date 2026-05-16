# Transcribe Module

## What This Module Does

The transcribe module takes an audio file and automatically converts the speech in it to text using OpenAI's Whisper AI model. It also analyzes the audio to detect the language and breaks the transcription into segments with timing information (start time, end time, and text for each part).

This is useful when you want to:
- Convert video or audio recordings into text
- Create subtitles or captions for videos
- Build searchable transcripts of interviews, lectures, or podcasts
- Extract spoken content for analysis or archival
- Create a semantic library of content with transcripts

## Quick Start

The simplest way to transcribe an audio file:

```bash
link2video --auto transcribe audio.wav --namespace my-transcript
```

This will create:
- `segments/my-transcript/my-transcript.json` — the complete transcription with timing data

The transcript will be in English by default. If the audio is in another supported language, you can specify it with `--language`.

## Full Command Syntax

```bash
link2video --auto transcribe <input_file> \
  --namespace <name> \
  [--output-dir <dir>] \
  [--model base] \
  [--language en] \
  [--device auto] \
  [--dry-run]
```

## Parameters Explained

### Required Parameters

**`<input_file>`** (positional argument)
- The path to your audio file
- Supported formats: WAV, MP3, M4A, FLAC, OGG, etc.
- Should contain speech (voice recording, interview, lecture, podcast, etc.)
- Examples: `./interview.wav`, `/home/user/audio.mp3`, `../recordings/podcast.m4a`

**`--namespace <name>`** (required)
- A label for your output file (no spaces or special characters, use hyphens)
- The output JSON will be named: `{namespace}.json`
- Examples: `--namespace interview-john`, `--namespace lecture-01`, `--namespace podcast-episode-5`

### Optional Parameters

**`--output-dir <dir>`** (default: `segments`)
- Where to save the transcription JSON file
- A folder named after your namespace will be created inside this directory
- Examples:
  - `--output-dir ./transcripts` → creates `./transcripts/my-transcript/`
  - `--output-dir /data/output` → creates `/data/output/my-transcript/`

**`--model tiny|base|small|medium|large`** (default: `base`)
- Which Whisper AI model to use. Different models trade off speed vs accuracy:
  - `tiny` — Fastest, least accurate (~39M parameters) - Good for quick rough drafts
  - `base` — Balanced, good for most uses (~74M parameters) - **Recommended**
  - `small` — Better accuracy (~244M parameters) - Good for important content
  - `medium` — High accuracy (~769M parameters) - Better for unclear audio
  - `large` — Best accuracy (~1550M parameters) - Slowest, use when accuracy is critical

Choose based on your needs:
- Quick processing: `--model tiny`
- Standard use: `--model base` (default, good balance)
- Important transcripts: `--model small` or `--model medium`
- Maximum accuracy: `--model large`

**`--language en|ja|pt`** (default: `en`)
- The language spoken in the audio
- `en` — English
- `ja` — Japanese
- `pt` — Portuguese
- The transcription will be more accurate if you specify the correct language
- Examples: `--language en`, `--language ja`, `--language pt`

**`--device auto|cpu|cuda|mps`** (default: `auto`)
- Which processor to use for transcription
- `auto` — Automatically detect: uses GPU (CUDA on servers, MPS on Mac) if available, falls back to CPU
- `cpu` — Always use CPU (slower, but works everywhere)
- `cuda` — Use NVIDIA GPU (only on Linux/Windows with NVIDIA GPU)
- `mps` — Use Apple Metal Performance Shaders (Mac only, faster on Apple Silicon)

You usually don't need to change this. `auto` works best:
- If you have a GPU (server with RTX 3090), it will use it automatically (fast)
- If you're on a Mac, it will use GPU if available (fast on M1/M2/M3 Macs)
- If neither, it falls back to CPU (slower but works)

Manually specify only if you know what you're doing:
- `--device cpu` to force CPU usage
- `--device cuda` if auto-detection isn't working on your GPU server

**`--dry-run`** (optional flag)
- Preview what will happen without actually running transcription
- Useful to check your parameters before committing to a long transcription job
- Transcription can take a while (especially with larger models), so use this to test first
- Example: Add `--dry-run` to see what would happen

## Output File

### Transcription JSON
`{namespace}.json`

A JSON file containing the complete transcription with all metadata. Here's an example of what it looks like:

```json
{
  "whisper_output": {
    "text": "Hello everyone. Today we're going to talk about machine learning...",
    "segments": [
      {
        "id": 0,
        "start": 0.0,
        "end": 2.5,
        "text": "Hello everyone.",
        "tokens": [50258, 50259, ...],
        "temperature": 0.0,
        "avg_logprob": -0.25,
        "compression_ratio": 1.2,
        "no_speech_prob": 0.001
      },
      {
        "id": 1,
        "start": 2.5,
        "end": 5.0,
        "text": "Today we're going to talk about machine learning",
        "tokens": [2714, 307, ...],
        "temperature": 0.0,
        "avg_logprob": -0.28,
        "compression_ratio": 1.2,
        "no_speech_prob": 0.0
      }
    ],
    "language": "en"
  },
  "model": "base",
  "device": "cuda",
  "timestamp": "2026-05-16T14:30:00Z",
  "input_file": "/path/to/audio.wav",
  "language_requested": "en"
}
```

**Understanding the output:**

- **`text`** — The complete transcription as a single string
- **`segments`** — Individual sentences or phrases with timing:
  - `start` / `end` — When in the audio (in seconds)
  - `text` — The words spoken during that time segment
  - `no_speech_prob` — How confident Whisper is there's actually speech (0=sure it's speech, 1=sure it's silence)
- **`language`** — The detected language (usually matches what you requested)
- **`model`** — Which Whisper model was used
- **`device`** — Which processor was used (cpu, cuda, or mps)
- **`timestamp`** — When the transcription was created

## Common Use Cases

### Case 1: Transcribe an Interview (Default Settings)

```bash
link2video --auto transcribe interview.wav --namespace interview-john-smith
```

Uses the default `base` model with English. Good for most interviews and conversations.

### Case 2: Transcribe a Podcast Episode with Better Accuracy

```bash
link2video --auto transcribe podcast.mp3 \
  --namespace podcast-ep-42 \
  --model medium
```

Uses the `medium` model for better accuracy on podcast audio (which might have background noise or multiple speakers).

### Case 3: Quick Rough Draft Transcription

```bash
link2video --auto transcribe speech.wav \
  --namespace rough-draft \
  --model tiny
```

Uses the fastest model for a quick rough transcription you can edit later.

### Case 4: Japanese Audio Transcription

```bash
link2video --auto transcribe japanese-lecture.wav \
  --namespace 日本語-講演 \
  --language ja \
  --model small
```

Specifies Japanese language and uses a smaller model for better accuracy with non-English speech.

### Case 5: Portuguese Audio Transcription

```bash
link2video --auto transcribe portuguese-interview.wav \
  --namespace entrevista-portugues \
  --language pt
```

Transcribes Portuguese audio. Uses default `base` model which works well for Portuguese.

### Case 6: Preview Before Transcribing (Slow Model)

```bash
# First, preview without actually transcribing (it's just checking settings)
link2video --auto transcribe important-meeting.wav \
  --namespace meeting-2026-05-16 \
  --model large \
  --dry-run

# If the preview looks good, run the actual transcription
link2video --auto transcribe important-meeting.wav \
  --namespace meeting-2026-05-16 \
  --model large
```

The `--dry-run` lets you verify your parameters without waiting for the `large` model to process (which can take a while).

### Case 7: GPU Server Batch Processing at Night

```bash
# On your GPU server with CUDA
link2video --auto transcribe audio1.wav --namespace transcript-01
link2video --auto transcribe audio2.wav --namespace transcript-02
link2video --auto transcribe audio3.wav --namespace transcript-03
```

Without specifying `--device`, it auto-detects and uses your CUDA GPU, making overnight batch processing fast.

## Processing Time Expectations

How long transcription takes (approximate, depends on audio):

| Model | Speed | Audio Length | Typical Time |
|-------|-------|--------------|--------------|
| tiny | Very Fast | 1 hour | 2 minutes (CPU) |
| base | Fast | 1 hour | 5-10 minutes (CPU) |
| small | Medium | 1 hour | 15-20 minutes (CPU) |
| medium | Slow | 1 hour | 30-40 minutes (CPU) |
| large | Very Slow | 1 hour | 1+ hour (CPU) |

**With GPU (much faster):** Divide times by 5-10 depending on your GPU

**Tip:** Use `--model tiny` or `--model base` for the best balance of speed and quality.

## Understanding Model Choices

### When to use each model:

**`tiny`** - When you need speed over accuracy
- Transcribing for a rough draft
- Testing parameters before running a larger model
- Processing lots of audio quickly
- Less important content

**`base`** - Recommended for most use cases
- Good accuracy, good speed
- Works well for interviews, lectures, podcasts
- Standard choice for building your semantic library

**`small`** - When accuracy is important
- Important meetings or lectures
- Audio with background noise
- Non-native speakers or accents
- Legal or archival purposes

**`medium`** - For very important content
- High-quality transcripts needed
- Audio with significant challenges
- Critical recordings that must be accurate

**`large`** - Maximum accuracy only
- Rare cases where speed doesn't matter
- Research or important documentation
- Complex audio with overlapping speakers

## Troubleshooting

### Error: "Whisper not installed"
**Solution:** Install the Whisper package
```bash
pip install openai-whisper
```

### Error: "Input file not found"
**Solution:** Check your file path
- Use absolute paths: `/home/user/audio/myfile.wav`
- Verify file exists: `ls -la yourfile.wav`

### Error: "Unsupported language"
**Solution:** Only English, Japanese, and Portuguese are supported
- Use `--language en` (English)
- Use `--language ja` (Japanese)
- Use `--language pt` (Portuguese)
- If your audio is in a different language, use English as fallback (it might still work partially)

### Error: "CUDA out of memory" or GPU error
**Solution:** Use a smaller model or CPU
```bash
# Use a smaller model with your GPU
link2video --auto transcribe audio.wav --namespace test --model base

# Or use CPU instead
link2video --auto transcribe audio.wav --namespace test --device cpu
```

### Transcription is taking too long
**Solution:** 
- Use a smaller model: `--model base` or `--model tiny`
- Use GPU if available: It will auto-detect, but verify with `--device auto`
- Process shorter audio files at a time

### Transcription is inaccurate or has lots of mistakes
**Solution:**
- Use a larger model: `--model medium` or `--model small`
- Make sure you specified the correct language
- Check if the audio is clear (loud background noise affects accuracy)
- Try with a different model to compare

### The JSON output file is very large
**Solution:** This is normal
- `base` model JSON is typically 50-100KB per hour of audio
- `large` model JSON can be larger
- You can compress it if needed: `gzip segments/my-transcript/my-transcript.json`

## Working with the JSON Output

The JSON output is structured and can be used by other tools:

### Extract just the text:
```bash
python3 << 'EOF'
import json
with open('segments/my-transcript/my-transcript.json') as f:
    data = json.load(f)
    full_text = data['whisper_output']['text']
    print(full_text)
EOF
```

### Create a simple transcript with timing:
```bash
python3 << 'EOF'
import json
with open('segments/my-transcript/my-transcript.json') as f:
    data = json.load(f)
    for segment in data['whisper_output']['segments']:
        start = segment['start']
        end = segment['end']
        text = segment['text']
        print(f"[{start:.1f}s - {end:.1f}s] {text}")
EOF
```

### Create an SRT subtitle file:
```bash
python3 << 'EOF'
import json
with open('segments/my-transcript/my-transcript.json') as f:
    data = json.load(f)
    with open('transcript.srt', 'w') as srt:
        for i, segment in enumerate(data['whisper_output']['segments'], 1):
            start = f"{int(segment['start']//3600):02d}:{int((segment['start']%3600)//60):02d}:{int(segment['start']%60):02d},000"
            end = f"{int(segment['end']//3600):02d}:{int((segment['end']%3600)//60):02d}:{int(segment['end']%60):02d},000"
            text = segment['text'].strip()
            srt.write(f"{i}\n{start} --> {end}\n{text}\n\n")
EOF
```

## Tips for Best Results

1. **Clear audio is important:** Whisper works best with clear speech. If your audio is very noisy, it may struggle.

2. **Specify the language:** Always use `--language` if you know the language. It significantly improves accuracy.

3. **Use appropriate model size:**
   - Start with `base` (default) for most things
   - Use `tiny` for quick drafts
   - Use `medium` or `large` only when accuracy is critical

4. **GPU makes it faster:** If you have GPU access, use it (auto-detection works). A 1-hour audio file takes minutes on GPU vs an hour on CPU.

5. **Test with dry-run first:** Use `--dry-run` to verify your parameters before starting a long transcription.

6. **Organize by namespace:** Use descriptive names like `interview-john-2026-05-16` to keep transcripts organized.

7. **Keep the JSON:** The JSON file contains all the information. You can extract text, create subtitles, or analyze segments anytime.

## What's Next?

After transcribing, you can:
- **Extract plain text:** Use Python scripts to get just the text from the JSON
- **Create subtitles:** Generate SRT/VTT files for videos
- **Analyze content:** Use the segments to find topics or keywords
- **Build a library:** Store transcripts organized by topic in your semantic library
- **Further processing:** Use transcripts with other AI tools for summarization, translation, or analysis
