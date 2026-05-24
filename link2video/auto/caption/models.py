from dataclasses import dataclass, field


@dataclass
class CaptionResult:
    global_summary: str
    model: str
    interval_seconds: float
    sequence_length: int
    length_seconds: float
    units: list
    context_used: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "global": self.global_summary,
            "model": self.model,
            "interval_seconds": self.interval_seconds,
            "sequence_length": self.sequence_length,
            "length": f"{self.length_seconds}s",
            "units": self.units,
            "context_used": self.context_used,
        }
