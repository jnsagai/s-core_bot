"""`scripts/install_refresh_timer.sh` renders opt-in user units (F011 FR-013, research R6)."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent.parent
SCRIPT = ROOT / "scripts" / "install_refresh_timer.sh"
NAME = "score-assistant-refresh"


@pytest.fixture
def fake_path(tmp_path: Path) -> tuple[dict[str, str], Path]:
    """PATH with a `systemctl` that only records calls, so tests can prove it is never used."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "systemctl-called"
    systemctl = bin_dir / "systemctl"
    systemctl.write_text(f'#!/bin/sh\necho "$@" >> {marker}\n')
    systemctl.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    return env, marker


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([str(SCRIPT), *args], env=env, capture_output=True, text=True)


def test_render_without_enable(tmp_path: Path, fake_path: tuple[dict[str, str], Path]) -> None:
    env, marker = fake_path
    units = tmp_path / "units"
    result = _run(env, "--unit-dir", str(units), "--no-enable", "--interval", "5min")
    assert result.returncode == 0, result.stderr
    service = (units / f"{NAME}.service").read_text()
    timer = (units / f"{NAME}.timer").read_text()
    assert "@" not in service and "@" not in timer
    assert (
        f"ExecStart={ROOT}/.venv/bin/score-assistant --config {ROOT}/config/local.yaml refresh"
        in service
    )
    assert f"WorkingDirectory={ROOT}" in service
    assert "OnUnitActiveSec=5min" in timer and "@INTERVAL@" not in timer
    assert not marker.exists()


@pytest.mark.skipif(shutil.which("systemd-analyze") is None, reason="systemd-analyze not installed")
def test_rendered_units_verify(tmp_path: Path, fake_path: tuple[dict[str, str], Path]) -> None:
    env, _ = fake_path
    units = tmp_path / "units"
    _run(env, "--unit-dir", str(units), "--no-enable")
    result = subprocess.run(
        [
            "systemd-analyze",
            "verify",
            "--user",
            str(units / f"{NAME}.service"),
            str(units / f"{NAME}.timer"),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_enable_calls_systemctl_user(
    tmp_path: Path, fake_path: tuple[dict[str, str], Path]
) -> None:
    env, marker = fake_path
    result = _run(env, "--unit-dir", str(tmp_path / "units"))
    assert result.returncode == 0, result.stderr
    calls = marker.read_text().splitlines()
    assert calls[:2] == ["--user daemon-reload", f"--user enable --now {NAME}.timer"]


def test_uninstall_removes_files(tmp_path: Path, fake_path: tuple[dict[str, str], Path]) -> None:
    env, marker = fake_path
    units = tmp_path / "units"
    _run(env, "--unit-dir", str(units), "--no-enable")
    result = _run(env, "--unit-dir", str(units), "--uninstall", "--no-enable")
    assert result.returncode == 0, result.stderr
    assert list(units.iterdir()) == [] and not marker.exists()


@pytest.mark.parametrize("interval", ["0min", "15 min", "1d", "abc"])
def test_bad_interval_rejected(
    tmp_path: Path, fake_path: tuple[dict[str, str], Path], interval: str
) -> None:
    env, _ = fake_path
    result = _run(env, "--unit-dir", str(tmp_path / "u"), "--no-enable", "--interval", interval)
    assert result.returncode == 2 and not (tmp_path / "u").exists()


def test_missing_config_rejected(tmp_path: Path, fake_path: tuple[dict[str, str], Path]) -> None:
    env, _ = fake_path
    result = _run(env, "--unit-dir", str(tmp_path / "u"), "--no-enable", "--config", "nope.yaml")
    assert result.returncode == 2
