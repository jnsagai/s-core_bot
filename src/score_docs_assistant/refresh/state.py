"""`data/refresh-state.json` (specs/015-scheduled-refresh/contracts/state-file.md).

One file, replaced atomically on every run except `busy`; it is never appended to, so polling
does not grow the data directory.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError

from score_docs_assistant.refresh.models import RefreshState

STATE_FILENAME = "refresh-state.json"


@dataclass(frozen=True)
class StateInvalid:
    """The file exists but cannot be used; refresh treats it as absent, doctor warns."""

    reason: str


def state_path(data_dir: Path) -> Path:
    return data_dir / STATE_FILENAME


def read_state(data_dir: Path) -> RefreshState | StateInvalid | None:
    path = state_path(data_dir)
    if not path.exists():
        return None
    try:
        return RefreshState.model_validate(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return StateInvalid(f"cannot read {path.name}: {exc}")
    except ValidationError as exc:
        return StateInvalid(f"{path.name} is invalid: {exc.error_count()} validation error(s)")


def write_state(data_dir: Path, state: RefreshState) -> Path:
    """temp file + fsync + os.replace: a crash leaves either the old state or the new one."""
    path = state_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = state.model_dump_json(indent=2) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    return path
