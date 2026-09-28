"""Run helpers in child processes for cross-process lock and pin tests."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent.parent

_HOLD_PIN = """
import sys, time
from pathlib import Path
from score_docs_assistant.storage.pins import Pin
pin = Pin(Path(sys.argv[1]), sys.argv[2])
Path(sys.argv[3]).write_text("held")
time.sleep(600)
"""

_HOLD_LOCK = """
import sys, time
from pathlib import Path
from score_docs_assistant.storage.locks import IngestLock
lock = IngestLock(Path(sys.argv[1])).acquire()
Path(sys.argv[2]).write_text("held")
time.sleep(600)
"""


def _spawn(code: str, *args: str, ready: Path) -> subprocess.Popen[bytes]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT / "src")}
    proc = subprocess.Popen([sys.executable, "-c", code, *args], env=env)
    deadline = time.monotonic() + 20
    while not ready.exists():
        if proc.poll() is not None or time.monotonic() > deadline:
            proc.kill()
            raise RuntimeError("helper process did not become ready")
        time.sleep(0.02)
    return proc


def hold_pin(data_dir: Path, snapshot_id: str, tmp: Path) -> subprocess.Popen[bytes]:
    ready = tmp / f"pin-{snapshot_id}.ready"
    return _spawn(_HOLD_PIN, str(data_dir), snapshot_id, str(ready), ready=ready)


def hold_ingest_lock(data_dir: Path, tmp: Path) -> subprocess.Popen[bytes]:
    ready = tmp / "lock.ready"
    return _spawn(_HOLD_LOCK, str(data_dir), str(ready), ready=ready)


def kill9(proc: subprocess.Popen[bytes]) -> None:
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=10)
