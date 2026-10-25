"""Local OCR for screenshot evidence.

Uses Apple's Vision framework through a tiny Swift binary.  Results are cached
on disk by file content hash, so a run is deterministic and repeatable.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "ocr"
BINARY = ROOT / "tools" / "ocr"


def _ensure_binary() -> bool:
    if BINARY.exists():
        return True
    src = ROOT / "tools" / "ocr.swift"
    if not src.exists():
        return False
    try:
        subprocess.run(
            ["swiftc", "-O", str(src), "-o", str(BINARY)],
            check=True,
            capture_output=True,
            timeout=180,
        )
        return BINARY.exists()
    except Exception:
        return False


def ocr_image(path: Path) -> str:
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    CACHE.mkdir(parents=True, exist_ok=True)
    cached = CACHE / f"{digest}.txt"
    if cached.exists():
        return cached.read_text(encoding="utf-8")
    text = ""
    if _ensure_binary():
        try:
            proc = subprocess.run(
                [str(BINARY), str(path)],
                capture_output=True,
                text=True,
                timeout=120,
            )
            if proc.returncode == 0:
                text = proc.stdout
        except Exception:
            text = ""
    cached.write_text(text, encoding="utf-8")
    return text
