"""Keep historical measurements verifiable as application code evolves."""
import hashlib
from pathlib import Path


def checked_names(hashes):
    if not hashes:
        raise ValueError("Empty source manifest")
    for name in hashes:
        if not name or name in (".", "..") or "/" in name or "\\" in name or ":" in name:
            raise ValueError(f"Unsafe source name: {name}")
    return hashes.keys()


def source_directory(run, hashes, current_root):
    """An existing archive must be complete; never hide corruption by falling back."""
    names = list(checked_names(hashes))
    archived = Path(run) / "source"
    root = archived if archived.exists() else Path(current_root)
    for name in names:
        path = root / name
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise ValueError(f"Measured source missing or hash mismatch: {path}")
    return root


def snapshot_sources(run, hashes, current_root):
    names = list(checked_names(hashes))
    blobs = {name: (Path(current_root) / name).read_bytes() for name in names}
    if any(hashlib.sha256(data).hexdigest() != hashes[name] for name, data in blobs.items()):
        raise ValueError("Source changed before snapshot")
    target = Path(run) / "source"
    target.mkdir(exist_ok=False)
    for name, data in blobs.items():
        (target / name).write_bytes(data)
