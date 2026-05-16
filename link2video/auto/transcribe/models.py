from dataclasses import dataclass, asdict
from typing import Any, Dict
import json


@dataclass
class Transcription:
    """
    Complete transcription result.

    Contains Whisper's native output plus minimal metadata for pipeline tracking.
    The 'whisper_output' dict preserves all fields from Whisper exactly as returned.
    """
    whisper_output: Dict[str, Any]
    model: str
    device: str
    timestamp: str
    input_file: str
    language_requested: str

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
