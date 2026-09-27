"""Hardware probe: psutil values mapped straight through; GPU detection via nvidia-smi
(research.md R11)."""

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from score_docs_assistant.diagnostics import hardware


def test_probe_hardware_maps_psutil_values(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        hardware.psutil, "virtual_memory", lambda: SimpleNamespace(total=1000, available=500)
    )
    monkeypatch.setattr(
        hardware.psutil, "disk_usage", lambda _path: SimpleNamespace(free=200, total=1000)
    )
    monkeypatch.setattr(hardware.psutil, "cpu_count", lambda: 8)
    monkeypatch.setattr(hardware, "probe_gpu", lambda: ([], "not_detected"))

    info = hardware.probe_hardware(tmp_path)
    assert info.ram_total_bytes == 1000
    assert info.ram_available_bytes == 500
    assert info.cpu_count == 8
    assert info.disk.free_bytes == 200
    assert info.disk.total_bytes == 1000


def test_probe_gpu_not_detected_when_nvidia_smi_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr(hardware.subprocess, "run", _raise)
    gpus, status = hardware.probe_gpu()
    assert gpus == []
    assert status == "not_detected"


def test_probe_gpu_error_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> None:
        raise subprocess.TimeoutExpired(cmd="nvidia-smi", timeout=3)

    monkeypatch.setattr(hardware.subprocess, "run", _raise)
    gpus, status = hardware.probe_gpu()
    assert gpus == []
    assert status == "error"


def test_probe_gpu_error_on_malformed_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stdout="not, a, valid, csv, line\n"),
    )
    gpus, status = hardware.probe_gpu()
    assert gpus == []
    assert status == "error"


def test_probe_gpu_detected_on_valid_csv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(
            returncode=0, stdout="NVIDIA GeForce RTX 4070 Laptop GPU, 8188, 8000\n"
        ),
    )
    gpus, status = hardware.probe_gpu()
    assert status == "detected"
    assert len(gpus) == 1
    assert gpus[0].name == "NVIDIA GeForce RTX 4070 Laptop GPU"
    assert gpus[0].memory_total_mib == 8188
    assert gpus[0].memory_free_mib == 8000
