import os
import json
from datetime import datetime
from typing import Optional

from .models import Transcription


class TranscribeProcessor:
    """Whisper orchestrator for audio transcription with validation and metadata."""

    SUPPORTED_LANGUAGES = {"en", "ja", "pt"}
    SUPPORTED_MODELS = {"tiny", "base", "small", "medium", "large"}

    def transcribe(
        self,
        audio_file: str,
        output_dir: str,
        namespace: str,
        model: str = "base",
        language: str = "en",
        device: str = "auto",
        dry_run: bool = False,
    ) -> Transcription:
        """
        Transcribe audio file using Whisper.

        Args:
            audio_file: Path to audio file
            output_dir: Root output directory
            namespace: Output filename prefix
            model: Whisper model to use
            language: Language code (en, ja, pt)
            device: Device to use (auto, cpu, cuda, mps)
            dry_run: Preview mode without processing

        Returns:
            Transcription object with results

        Raises:
            FileNotFoundError: If audio file doesn't exist
            ValueError: If parameters are invalid
            RuntimeError: If Whisper processing fails
        """
        if not os.path.isfile(audio_file):
            raise FileNotFoundError(f"Audio file not found: {audio_file}")

        if language not in self.SUPPORTED_LANGUAGES:
            raise ValueError(
                f"Unsupported language: {language}. "
                f"Supported: {', '.join(self.SUPPORTED_LANGUAGES)}"
            )

        if model not in self.SUPPORTED_MODELS:
            raise ValueError(
                f"Unsupported model: {model}. "
                f"Supported: {', '.join(self.SUPPORTED_MODELS)}"
            )

        if device not in {"auto", "cpu", "cuda", "mps"}:
            raise ValueError(
                f"Unsupported device: {device}. "
                f"Supported: auto, cpu, cuda, mps"
            )

        # Create output directory
        namespace_dir = os.path.join(output_dir, namespace)
        if not dry_run:
            os.makedirs(namespace_dir, exist_ok=True)

        output_path = os.path.join(namespace_dir, f"{namespace}.json")

        if dry_run:
            print(f"[DRY-RUN] Would transcribe {audio_file} with model={model}, language={language}")
            print(f"[DRY-RUN] Would save result to: {output_path}")
            return Transcription(
                whisper_output={"text": "", "segments": []},
                model=model,
                device="cpu",
                timestamp=datetime.utcnow().isoformat() + "Z",
                input_file=audio_file,
                language_requested=language,
            )

        # Detect device
        actual_device = self._detect_device(device)
        print(f"Using device: {actual_device}")

        # Import and run Whisper
        try:
            import whisper
        except ImportError:
            raise RuntimeError(
                "Whisper not installed. Install with: pip install openai-whisper"
            )

        try:
            print(f"Loading Whisper model: {model}")
            whisper_model = whisper.load_model(model, device=actual_device)

            print(f"Transcribing audio (language: {language})...")
            result = whisper_model.transcribe(audio_file, language=language)

        except Exception as e:
            raise RuntimeError(f"Whisper transcription failed: {e}")

        # Create Transcription object
        transcription = Transcription(
            whisper_output=result,
            model=model,
            device=actual_device,
            timestamp=datetime.utcnow().isoformat() + "Z",
            input_file=audio_file,
            language_requested=language,
        )

        # Save JSON output
        print(f"Saving transcription to: {output_path}")
        with open(output_path, "w") as f:
            f.write(transcription.to_json())

        print("Transcription complete!")
        return transcription

    def _detect_device(self, requested_device: str) -> str:
        """
        Detect and select the appropriate device.

        Args:
            requested_device: User-requested device (auto, cpu, cuda, mps)

        Returns:
            Actual device to use (cpu, cuda, or mps)
        """
        if requested_device != "auto":
            return requested_device

        # Auto-detect: prefer GPU if available
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
        except ImportError:
            pass

        # Check for Apple Metal Performance Shaders
        try:
            import torch

            if torch.backends.mps.is_available():
                return "mps"
        except (ImportError, AttributeError):
            pass

        # Fallback to CPU
        return "cpu"
