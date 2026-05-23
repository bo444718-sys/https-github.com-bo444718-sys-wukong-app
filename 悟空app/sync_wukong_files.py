#!/usr/bin/env python3
"""Build a live file inventory for Wukong app and PWA surfaces."""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import time
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_ROOT = Path("/Users/wangbo/Documents/New project/悟空app")
ROOT = Path(os.getenv("WUKONG_PROJECT_ROOT") or DEFAULT_ROOT)
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent
HERMES_PWA = Path("/Users/wangbo/.hermes/wukong_pwa")
HERMES_TELEGRAM = Path("/Users/wangbo/.hermes/wukong_telegram")
OUTPUT_NAME = "wukong_file_sync.json"

SKIP_PARTS = {
    ".build",
    ".build-appstore-check",
    ".build-cache",
    ".git",
    ".playwright-cli",
    ".pycache",
    "android",
    "node_modules",
    "Wukong.app",
    "Wukong.xcodeproj",
}
SKIP_PART_PREFIXES = (".pycache", ".pytest_cache")
SKIP_SUFFIXES = {".DS_Store", ".log", ".zip"}
SKIP_FILES = {"package_ios_signing_kit.py"}
TEXT_SUFFIXES = {
    ".swift",
    ".py",
    ".js",
    ".css",
    ".html",
    ".md",
    ".json",
    ".plist",
    ".yml",
    ".yaml",
    ".sh",
    ".txt",
    ".webmanifest",
}


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    if any(part in SKIP_PARTS for part in rel.parts):
        return True
    if any(part.startswith(SKIP_PART_PREFIXES) for part in rel.parts):
        return True
    if path.name.startswith(".env") and not path.name.endswith(".example"):
        return True
    if path.name.endswith("-debug.apk"):
        return True
    if path.suffix in SKIP_SUFFIXES or path.name == OUTPUT_NAME or path.name in SKIP_FILES:
        return True
    return False


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def text_preview(path: Path, limit: int = 900) -> str:
    if path.suffix not in TEXT_SUFFIXES and path.name != "Package.swift":
        return ""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    text = "\n".join(line.rstrip() for line in text.splitlines()[:28])
    return text[:limit]


def role_for(path: Path) -> str:
    rel = str(path.relative_to(ROOT))
    if rel.startswith("Sources/") or rel == "Package.swift":
        return "Apple App"
    if rel.startswith("PWA/") or rel in {"PWA_INSTALL.md", "start_wukong_pwa.py", "stop_wukong_pwa.py"}:
        return "网页下载端"
    if "telegram" in rel.lower() or rel.startswith("ai.wukong.telegram"):
        return "Telegram"
    if rel.endswith(".plist") or rel.endswith(".sh") or rel.endswith(".py"):
        return "自动化"
    if rel.endswith(".md"):
        return "文档"
    if rel.endswith(".json") or rel.endswith(".txt"):
        return "同步数据"
    return "资源"


def build_inventory() -> dict:
    files = []
    for path in sorted(ROOT.rglob("*")):
        if not path.is_file() or should_skip(path):
            continue
        stat = path.stat()
        rel = str(path.relative_to(ROOT))
        files.append(
            {
                "path": rel,
                "role": role_for(path),
                "bytes": stat.st_size,
                "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                "sha256": sha256(path),
                "mime": mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                "preview": text_preview(path),
            }
        )
    roles: dict[str, int] = {}
    for item in files:
        roles[item["role"]] = roles.get(item["role"], 0) + 1
    return {
        "app": "悟空",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "fileCount": len(files),
        "totalBytes": sum(item["bytes"] for item in files),
        "roles": roles,
        "files": files,
    }


def write_outputs(payload: dict) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for target in [
        ROOT / OUTPUT_NAME,
        ROOT / "PWA" / OUTPUT_NAME,
        HERMES_PWA / OUTPUT_NAME,
        HERMES_PWA / "PWA" / OUTPUT_NAME,
        HERMES_TELEGRAM / OUTPUT_NAME,
    ]:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding="utf-8")


def main() -> int:
    payload = build_inventory()
    write_outputs(payload)
    print(f"Synced {payload['fileCount']} Wukong files into {OUTPUT_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
