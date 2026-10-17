"""Project persistence: one JSON file per project, isolated per project, deletable in one step."""
from __future__ import annotations

import os
try:
    import fcntl
except ImportError:  # Windows desktop quick start
    fcntl = None
    import msvcrt
import tempfile
from contextlib import contextmanager
from pathlib import Path

from .model import Project


class ProjectConflict(Exception):
    """The project changed since it was loaded. Never overwrite another employee's work."""


class ProjectStore:
    def __init__(self, root: str | Path | None = None):
        self.root = Path(root or os.environ.get("GRIDEASE_DATA", "data")) / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, pid: str) -> Path:
        if not pid.isalnum():
            raise KeyError(pid)
        return self.root / f"{pid}.json"

    @contextmanager
    def _lock(self, pid):
        with self._path(pid).with_suffix(".lock").open("a+") as lock:
            if fcntl is not None:
                fcntl.flock(lock, fcntl.LOCK_EX)
            else:
                lock.seek(0)
                if lock.read(1) == "":
                    lock.write("0")
                    lock.flush()
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(lock, fcntl.LOCK_UN)
                else:
                    lock.seek(0)
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)

    def save(self, p: Project) -> Project:
        path = self._path(p.id)
        with self._lock(p.id):
            existing = self.load(p.id) if path.exists() else None
            if (existing is not None and existing.revision != p.revision) or (existing is None and p.revision != 0):
                raise ProjectConflict("This project was changed or deleted by another request. Reload the project and retry.")
            updated = p.model_copy(deep=True)
            updated.revision += 1
            temp_path = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.root, suffix=".tmp", delete=False) as tmp:
                    temp_path = Path(tmp.name)
                    tmp.write(updated.model_dump_json(indent=1))
                    tmp.flush()
                    os.fsync(tmp.fileno())
                temp_path.replace(path)
            finally:
                if temp_path is not None:
                    temp_path.unlink(missing_ok=True)
            p.revision = updated.revision
        return p

    def load(self, pid: str) -> Project:
        path = self._path(pid)
        if not path.exists():
            raise KeyError(pid)
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def list(self) -> list[Project]:
        return [Project.model_validate_json(f.read_text(encoding="utf-8")) for f in sorted(self.root.glob("*.json"))]

    def delete(self, pid: str) -> None:
        with self._lock(pid):
            self._path(pid).unlink(missing_ok=False)
