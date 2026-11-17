"""Google Drive source using the REST API directly (no heavyweight SDK).

Auth: set GOOGLE_ACCESS_TOKEN (e.g. from a service account via
`gcloud auth print-access-token`), or plug in your own token provider.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

import httpx

from ..models import Clip
from . import infer_metadata

API = "https://www.googleapis.com/drive/v3"


class DriveSource:
    def __init__(self, folder_id: str, extensions: list[str], token: str | None = None,
                 cache_dir: Path | None = None, client: httpx.Client | None = None):
        self.folder_id = folder_id
        self.extensions = {e.lower() for e in extensions}
        self.token = token or os.environ.get("GOOGLE_ACCESS_TOKEN", "")
        self.cache_dir = cache_dir or Path(tempfile.gettempdir()) / "clip-autopilot"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.client = client or httpx.Client(timeout=60)

    @property
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def _list(self) -> Iterable[dict]:
        params = {
            "q": f"'{self.folder_id}' in parents and trashed = false",
            "fields": "nextPageToken, files(id, name, md5Checksum, mimeType)",
            "pageSize": 100,
        }
        while True:
            r = self.client.get(f"{API}/files", params=params, headers=self._headers)
            r.raise_for_status()
            data = r.json()
            yield from data.get("files", [])
            if not (tok := data.get("nextPageToken")):
                return
            params["pageToken"] = tok

    def _download(self, file_id: str, name: str) -> Path:
        dest = self.cache_dir / f"{file_id}_{name}"
        if dest.exists():
            return dest
        with self.client.stream("GET", f"{API}/files/{file_id}", params={"alt": "media"},
                                headers=self._headers) as r:
            r.raise_for_status()
            with dest.open("wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        return dest

    def discover(self) -> Iterable[Clip]:
        for f in self._list():
            if Path(f["name"]).suffix.lower() not in self.extensions:
                continue
            game, tags = infer_metadata(f["name"])
            yield Clip(
                id=f["id"],
                name=f["name"],
                path=self._download(f["id"], f["name"]),
                content_hash=f.get("md5Checksum") or f["id"],
                game=game,
                tags=tags,
            )
