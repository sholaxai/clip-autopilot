from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol

from ..config import SourceConfig
from ..models import Clip

KNOWN_GAMES = {
    "warzone": "Warzone",
    "wz": "Warzone",
    "mw4": "MW4",
    "gta": "GTA 6",
    "gta6": "GTA 6",
}


class ClipSource(Protocol):
    def discover(self) -> Iterable[Clip]: ...


def file_hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.blake2b(digest_size=16)
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def infer_metadata(name: str) -> tuple[str | None, list[str]]:
    """Pull game + tags out of filenames like `wz_quad-wipe_clutch.mp4`."""
    tokens = [t for t in re.split(r"[\s_\-.]+", Path(name).stem.lower()) if t]
    game = next((KNOWN_GAMES[t] for t in tokens if t in KNOWN_GAMES), None)
    tags = [t for t in tokens if t not in KNOWN_GAMES and not t.isdigit() and len(t) > 2]
    return game, tags


class LocalFolderSource:
    def __init__(self, root: Path, extensions: list[str]):
        self.root = root
        self.extensions = {e.lower() for e in extensions}

    def discover(self) -> Iterable[Clip]:
        for p in sorted(self.root.rglob("*")):
            if p.is_file() and p.suffix.lower() in self.extensions:
                game, tags = infer_metadata(p.name)
                digest = file_hash(p)
                yield Clip(id=digest[:12], name=p.name, path=p, content_hash=digest,
                           game=game, tags=tags)


def build_source(cfg: SourceConfig) -> ClipSource:
    if cfg.kind == "local":
        if not cfg.path:
            raise ValueError("source.path is required for local sources")
        return LocalFolderSource(cfg.path, cfg.extensions)
    if cfg.kind == "gdrive":
        from .gdrive import DriveSource

        if not cfg.folder_id:
            raise ValueError("source.folder_id is required for gdrive sources")
        return DriveSource(cfg.folder_id, cfg.extensions)
    raise ValueError(f"unknown source kind {cfg.kind}")
