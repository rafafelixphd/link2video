# link2video/auto/caption/processor.py
import base64
import re
import subprocess
import tempfile
from pathlib import Path

import ollama

from link2video.auto.caption.models import CaptionResult
from link2video.metadata_manager import MetadataManager

try:
    import yaml as _yaml
except ImportError:
    _yaml = None

_CONTEXT_KEY_MAP = {
    "transcription": "link2video/auto/transcribe",
    "comments": "link2video/download",
}


class CaptionProcessor:
    def __init__(self, ollama_url: str = "http://debugx.local/ollama") -> None:
        self._client = ollama.Client(host=ollama_url)

    def caption(
        self,
        video_path: str,
        interval_seconds: float = 1.0,
        sequence_length: int = 3,
        model: str = "llava",
        additional_query: str = "",
        context_sections: list | None = None,
        dry_run: bool = False,
    ) -> CaptionResult:
        if dry_run:
            return CaptionResult(
                global_summary="",
                model=model,
                interval_seconds=interval_seconds,
                sequence_length=sequence_length,
                length_seconds=0.0,
                units=[],
                context_used=[],
            )

        video = Path(video_path)
        if not video.is_file():
            raise FileNotFoundError(f"Video not found: {video_path}")

        yaml_context = self._load_yaml_context(video_path, context_sections or [])
        duration = self._get_video_duration(video_path)

        with tempfile.TemporaryDirectory() as tmp_dir:
            self._extract_frames(video_path, tmp_dir, interval_seconds)
            frame_files = sorted(Path(tmp_dir).glob("frame_*.jpg"))

            units = []
            accumulated_captions: list[str] = []

            for batch_start in range(0, len(frame_files), sequence_length):
                batch = frame_files[batch_start: batch_start + sequence_length]
                images = [self._encode_frame(str(f)) for f in batch]
                prompt = self._build_batch_prompt(
                    batch_index=batch_start,
                    batch_size=len(batch),
                    yaml_context=yaml_context,
                    additional_query=additional_query,
                    accumulated_captions=accumulated_captions,
                )
                response = self._call_ollama(model=model, prompt=prompt, images=images)
                descriptions = self._parse_frame_descriptions(response, expected_count=len(batch))

                for i, desc in enumerate(descriptions):
                    timestamp = round((batch_start + i) * interval_seconds, 3)
                    units.append({"timestamp": timestamp, "description": desc})
                    accumulated_captions.append(f"Frame {batch_start + i + 1} ({timestamp}s): {desc}")

        summary_prompt = self._build_summary_prompt(yaml_context, additional_query, accumulated_captions)
        global_summary = self._call_ollama(model=model, prompt=summary_prompt)

        context_used = [s for s in (context_sections or []) if s in yaml_context]

        result = CaptionResult(
            global_summary=global_summary,
            model=model,
            interval_seconds=interval_seconds,
            sequence_length=sequence_length,
            length_seconds=round(duration, 3),
            units=units,
            context_used=context_used,
        )

        MetadataManager().update(video_path, "link2video/auto/caption", result.to_dict())
        return result

    def _load_yaml_context(self, video_path: str, context_sections: list) -> dict:
        if not context_sections or _yaml is None:
            return {}
        yaml_path = Path(video_path).with_suffix(".yaml")
        if not yaml_path.exists():
            return {}
        data = _yaml.safe_load(yaml_path.read_text()) or {}
        context = {}
        for section in context_sections:
            yaml_key = _CONTEXT_KEY_MAP.get(section)
            if yaml_key and yaml_key in data:
                if section == "comments":
                    context["comments"] = data[yaml_key].get("comments", "")
                else:
                    context[section] = data[yaml_key]
        return context

    def _build_batch_prompt(
        self,
        batch_index: int,
        batch_size: int,
        yaml_context: dict,
        additional_query: str,
        accumulated_captions: list[str],
    ) -> str:
        parts = []
        if yaml_context:
            parts.append("== Video Metadata ==")
            if "transcription" in yaml_context:
                text = yaml_context["transcription"].get("text", "")
                parts.append(f"Transcript: {text}")
            if "comments" in yaml_context:
                parts.append(f"Comments: {yaml_context['comments']}")
            parts.append("")
        if accumulated_captions:
            parts.append("== Previous frame descriptions ==")
            parts.extend(accumulated_captions)
            parts.append("")
        if additional_query:
            parts.append(f"Additional context: {additional_query}")
            parts.append("")
        parts.append(
            f"You are analyzing a video. Describe what you see in each of the {batch_size} images below. "
            "Return exactly one description per image in this format:\n"
            + "\n".join(f"Frame {batch_index + i + 1}: <description>" for i in range(batch_size))
        )
        return "\n".join(parts)

    def _build_summary_prompt(
        self, yaml_context: dict, additional_query: str, accumulated_captions: list[str]
    ) -> str:
        parts = []
        if yaml_context:
            parts.append("== Video Metadata ==")
            if "transcription" in yaml_context:
                text = yaml_context["transcription"].get("text", "")
                parts.append(f"Transcript: {text}")
            if "comments" in yaml_context:
                parts.append(f"Comments: {yaml_context['comments']}")
            parts.append("")
        parts.append("== Per-frame descriptions ==")
        parts.extend(accumulated_captions)
        parts.append("")
        if additional_query:
            parts.append(f"Additional query: {additional_query}")
            parts.append("")
        parts.append(
            "Based on the above, write a concise overall summary of this video's content."
        )
        return "\n".join(parts)

    def _get_video_duration(self, video_path: str) -> float:
        result = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                video_path,
            ],
            capture_output=True, text=True, check=True,
        )
        return float(result.stdout.strip())

    def _extract_frames(self, video_path: str, out_dir: str, interval_seconds: float) -> None:
        subprocess.run(
            [
                "ffmpeg", "-i", video_path,
                "-vf", f"fps=1/{interval_seconds}",
                "-q:v", "2",
                str(Path(out_dir) / "frame_%04d.jpg"),
            ],
            check=True, capture_output=True,
        )

    def _encode_frame(self, frame_path: str) -> str:
        with open(frame_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def _call_ollama(self, model: str, prompt: str, images: list | None = None) -> str:
        kwargs = {"model": model, "prompt": prompt}
        if images:
            kwargs["images"] = images
        response = self._client.generate(**kwargs)
        return response["response"]

    def _parse_frame_descriptions(self, text: str, expected_count: int) -> list:
        pattern = re.compile(r"Frame\s+\d+:\s*(.+?)(?=Frame\s+\d+:|$)", re.DOTALL | re.IGNORECASE)
        matches = pattern.findall(text)
        descriptions = [m.strip() for m in matches]
        while len(descriptions) < expected_count:
            descriptions.append("[parse error]")
        return descriptions[:expected_count]
