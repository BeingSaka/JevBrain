import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .normalize import EngineError

class JsonlLogger:
    def __init__(self, path): self.path = Path(path)
    def write(self, event):
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a", encoding="utf-8") as f:
                f.write(json.dumps({"timestamp": datetime.now(timezone.utc).isoformat(), **event},
                                   ensure_ascii=False, allow_nan=False)+"\n")
        except OSError: raise EngineError("Evaluation log unavailable; execution stopped") from None
