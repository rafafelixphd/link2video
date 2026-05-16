from abc import ABC, abstractmethod
from typing import List, NamedTuple


class Segment(NamedTuple):
    """Represents a video segment."""
    segment_id: int
    start: float
    end: float
    filepath: str
    metadata_path: str


class SplitProcessor(ABC):
    """Abstract base class for video splitting strategies."""

    @abstractmethod
    def split(
        self,
        input_file: str,
        output_dir: str,
        namespace: str,
        **kwargs
    ) -> List[Segment]:
        """
        Split video and return list of Segment objects.

        Args:
            input_file: Path to input video file.
            output_dir: Root directory where namespace folders are created.
            namespace: Folder name and filename prefix for outputs.
            **kwargs: Additional processor-specific arguments.

        Returns:
            List of Segment objects representing the split parts.
        """
        raise NotImplementedError
