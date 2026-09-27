"""RAM, disk, and GPU probing (research.md R11)."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import psutil

GpuDetection = Literal["detected", "not_detected", "error"]

_NVIDIA_SMI_ARGV = [
    "nvidia-smi",
    "--query-gpu=name,memory.total,memory.free",
    "--format=csv,noheader,nounits",
]


@dataclass(frozen=True)
class GpuInfo:
    name: str
    memory_total_mib: int
    memory_free_mib: int


@dataclass(frozen=True)
class DiskInfo:
    path: str
    free_bytes: int
    total_bytes: int
    is_fallback: bool


@dataclass(frozen=True)
class HardwareInfo:
    os: str
    arch: str
    cpu_count: int
    ram_total_bytes: int
    ram_available_bytes: int
    gpus: list[GpuInfo]
    gpu_detection: GpuDetection
    disk: DiskInfo


def probe_gpu() -> tuple[list[GpuInfo], GpuDetection]:
    try:
        result = subprocess.run(  # noqa: S603 - fixed argv, shell=False, no document content
            _NVIDIA_SMI_ARGV, capture_output=True, text=True, timeout=3, shell=False, check=False
        )
    except FileNotFoundError:
        return [], "not_detected"
    except subprocess.TimeoutExpired:
        return [], "error"
    if result.returncode != 0:
        return [], "not_detected"
    gpus: list[GpuInfo] = []
    try:
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            name, total, free = (part.strip() for part in line.split(","))
            gpus.append(GpuInfo(name=name, memory_total_mib=int(total), memory_free_mib=int(free)))
    except ValueError:
        return [], "error"
    if not gpus:
        return [], "not_detected"
    return gpus, "detected"


def probe_hardware(disk_path: Path) -> HardwareInfo:
    vm = psutil.virtual_memory()
    du = psutil.disk_usage(str(disk_path))
    gpus, gpu_detection = probe_gpu()
    return HardwareInfo(
        os=platform.system(),
        arch=platform.machine(),
        cpu_count=psutil.cpu_count() or 0,
        ram_total_bytes=vm.total,
        ram_available_bytes=vm.available,
        gpus=gpus,
        gpu_detection=gpu_detection,
        disk=DiskInfo(
            path=str(disk_path), free_bytes=du.free, total_bytes=du.total, is_fallback=False
        ),
    )
