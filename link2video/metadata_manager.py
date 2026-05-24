import os
import shutil
import tempfile
from datetime import date
from pathlib import Path

import yaml


class MetadataManager:
    def update(self, video_path: str, section_key: str, data: dict) -> str:
        """Read existing YAML alongside video_path, merge section_key, write back atomically."""
        yaml_path = Path(video_path).with_suffix(".yaml")

        existing = {}
        if yaml_path.exists():
            with open(yaml_path, "r") as f:
                existing = yaml.safe_load(f) or {}

        if "name" not in existing:
            existing["name"] = Path(video_path).stem
        if "original_file" not in existing:
            existing["original_file"] = str(video_path)
        if "date" not in existing:
            existing["date"] = str(date.today())

        existing[section_key] = data

        fd, tmp = tempfile.mkstemp(dir=yaml_path.parent, suffix=".yaml.tmp")
        try:
            with os.fdopen(fd, "w") as f:
                yaml.safe_dump(
                    existing, f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                )
            shutil.move(tmp, str(yaml_path))
        except Exception:
            if os.path.exists(tmp):
                os.unlink(tmp)
            raise

        return str(yaml_path)
