#!/usr/bin/env python3
"""Package Wukong iOS signing materials for another Mac with Xcode."""

from __future__ import annotations

import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "PWA" / "downloads" / "wukong-ios-signing-kit.zip"
INCLUDE_PATHS = [
    "AppStore",
    "Resources",
    "Sources",
    "iOS",
    "scripts/apple_sign_check.sh",
    "scripts/build_app_store.sh",
    "scripts/build_signed_ios.sh",
    "Package.swift",
    "project.yml",
    "Wukong.xcodeproj",
    "README.md",
]


def add_path(zf: zipfile.ZipFile, path: Path) -> None:
    if not path.exists():
        return
    if path.is_file():
        zf.write(path, path.relative_to(ROOT))
        return
    for item in sorted(path.rglob("*")):
        if item.is_file():
            zf.write(item, item.relative_to(ROOT))


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE_PATHS:
            add_path(zf, ROOT / rel)
        handoff = "\n".join(
            [
                "# 悟空 Apple 签名包",
                "",
                f"生成时间：{datetime.now(timezone.utc).isoformat()}",
                "",
                "在有完整 Xcode 和 Apple Developer 账号的 Mac 上执行：",
                "",
                "```bash",
                "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer",
                "./scripts/apple_sign_check.sh",
                "APPLE_TEAM_ID=你的TeamID ./scripts/build_signed_ios.sh app-store",
                "```",
                "",
                "Bundle ID: ai.wukong.app",
                "App 名称：悟空",
                "",
            ]
        )
        zf.writestr("SIGNING_HANDOFF.md", handoff)
    print(f"Apple signing kit: {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
