import contextlib
import hashlib
import json
import os
import tempfile
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import redis

from app.config import Settings


class CacheStore:
    """Unified Redis + atomic disk cache with LRU pruning and pipeline_version keying."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = Path(settings.cache_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "cutouts").mkdir(parents=True, exist_ok=True)
        (self.root / "json").mkdir(parents=True, exist_ok=True)
        self._redis: redis.Redis | None = None
        try:
            client = redis.Redis.from_url(
                settings.redis_url,
                socket_connect_timeout=0.3,
                socket_timeout=0.5,
                decode_responses=True,
            )
            client.ping()
            self._redis = client
        except Exception:
            self._redis = None

    def redis_available(self) -> bool:
        if self._redis is None:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            return False

    def versioned_key(self, raw_key: str) -> str:
        return f"v{self.settings.pipeline_version}:{raw_key}"

    @staticmethod
    def _hash_key(namespace: str, key: str) -> str:
        return hashlib.sha256(f"{namespace}:{key}".encode()).hexdigest()

    def _json_path(self, namespace: str, key: str) -> Path:
        h = self._hash_key(namespace, key)
        return self.root / "json" / f"{namespace}_{h}.json"

    def get_json(self, namespace: str, key: str) -> dict[str, Any] | None:
        full_key = f"{namespace}:{key}"
        if self._redis is not None:
            try:
                raw = self._redis.get(full_key)
                if raw:
                    return json.loads(raw)  # type: ignore[no-any-return]
            except Exception:
                pass

        p = self._json_path(namespace, key)
        if not p.exists():
            return None
        try:
            envelope = json.loads(p.read_text(encoding="utf-8"))
            expires_at = envelope.get("expires_at")
            if expires_at is not None and time.time() > float(expires_at):
                p.unlink(missing_ok=True)
                return None
            os.utime(p, None)
            return envelope.get("data")  # type: ignore[no-any-return]
        except Exception:
            return None

    def set_json(
        self,
        namespace: str,
        key: str,
        value: dict[str, Any],
        ttl_seconds: int | None = None,
    ) -> None:
        ttl = ttl_seconds if ttl_seconds is not None else self.settings.cache_ttl_seconds
        full_key = f"{namespace}:{key}"
        if self._redis is not None:
            with contextlib.suppress(Exception):
                self._redis.setex(full_key, ttl, json.dumps(value))
        p = self._json_path(namespace, key)
        envelope = {
            "cached_at": datetime.now(UTC).isoformat(),
            "expires_at": (time.time() + ttl) if ttl > 0 else None,
            "data": value,
        }
        self._atomic_write_bytes(p, json.dumps(envelope).encode("utf-8"))
        self._prune_if_needed()

    def cutout_path(
        self,
        obs_id: str,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        release: str,
        provenance_version: str,
    ) -> Path:
        raw = (
            f"{obs_id}:{round(ra_deg, 5):.5f}:{round(dec_deg, 5):.5f}:"
            f"{round(fov_deg, 4):.4f}:{release}:{provenance_version}"
        )
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return self.root / "cutouts" / f"{digest}.fits"

    def get_cutout_path(
        self,
        obs_id: str,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        release: str,
        provenance_version: str,
    ) -> Path | None:
        p = self.cutout_path(obs_id, ra_deg, dec_deg, fov_deg, release, provenance_version)
        if p.exists() and p.stat().st_size > 0:
            os.utime(p, None)
            return p
        return None

    def put_cutout_bytes(
        self,
        obs_id: str,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        release: str,
        provenance_version: str,
        data: bytes,
    ) -> Path:
        p = self.cutout_path(obs_id, ra_deg, dec_deg, fov_deg, release, provenance_version)
        self._atomic_write_bytes(p, data)
        self._prune_if_needed()
        return p

    def _atomic_write_bytes(self, dest: Path, data: bytes) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent), prefix=".tmp_")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)
            os.replace(tmp_name, dest)
        except Exception:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    def _prune_if_needed(self) -> None:
        max_bytes = self.settings.disk_cache_max_mb * 1024 * 1024
        files: list[tuple[float, int, Path]] = []
        total = 0
        for sub in ("cutouts", "json"):
            d = self.root / sub
            if not d.exists():
                continue
            for p in d.iterdir():
                if p.is_file() and not p.name.startswith(".tmp_"):
                    st = p.stat()
                    total += st.st_size
                    files.append((st.st_mtime, st.st_size, p))
        if total <= max_bytes:
            return
        files.sort(key=lambda item: item[0])  # oldest mtime first
        for _, sz, p in files:
            if total <= max_bytes * 0.85:
                break
            p.unlink(missing_ok=True)
            total -= sz
