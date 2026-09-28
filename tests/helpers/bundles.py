"""Build hostile bundle archives in tmp_path from a valid exported bundle."""

from __future__ import annotations

import io
import json
import tarfile
from collections.abc import Callable
from pathlib import Path

Member = tuple[tarfile.TarInfo, bytes | None]


def read_members(path: Path) -> list[Member]:
    members: list[Member] = []
    with tarfile.open(path, "r:gz") as tar:
        for info in tar.getmembers():
            handle = tar.extractfile(info) if info.isreg() else None
            members.append((info, handle.read() if handle else None))
    return members


def write_members(path: Path, members: list[Member]) -> Path:
    with tarfile.open(path, "w:gz", format=tarfile.PAX_FORMAT) as tar:
        for info, data in members:
            if data is not None:
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            else:
                tar.addfile(info)
    return path


def manifest_of(members: list[Member]) -> dict:  # type: ignore[type-arg]
    return json.loads(members[0][1] or b"{}")


def with_manifest(members: list[Member], update: Callable[[dict], None]) -> list[Member]:  # type: ignore[type-arg]
    data = manifest_of(members)
    update(data)
    info = members[0][0]
    return [(info, json.dumps(data).encode()), *members[1:]]


def extra(name: str, data: bytes = b"x", kind: bytes = tarfile.REGTYPE, link: str = "") -> Member:
    info = tarfile.TarInfo(name)
    info.type = kind
    info.linkname = link
    info.mode = 0o644
    return (info, data if kind == tarfile.REGTYPE else None)
