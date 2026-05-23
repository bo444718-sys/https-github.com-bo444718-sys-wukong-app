#!/usr/bin/env python3
"""Regenerate, publish, restart, and self-check the Wukong PWA runtime."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PWA = ROOT / "PWA"
HERMES_PWA = Path("/Users/wangbo/.hermes/wukong_pwa")
PUBLISH = HERMES_PWA / "PWA"
HERMES_TELEGRAM = Path("/Users/wangbo/.hermes/wukong_telegram")
HERMES_WUKONG = Path("/Users/wangbo/.hermes/wukong")


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=str(ROOT), text=True, check=check)


def copy_files(files: list[str], source_root: Path, target_root: Path) -> None:
    target_root.mkdir(parents=True, exist_ok=True)
    for rel in files:
        source = source_root / rel
        target = target_root / rel
        if not source.exists():
            raise FileNotFoundError(source)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def regenerate() -> None:
    runtime_url = HERMES_PWA / "wukong_pwa_url.txt"
    local_url = ROOT / "wukong_pwa_url.txt"
    if runtime_url.exists():
        local_url.write_text(runtime_url.read_text(encoding="utf-8").strip() + "\n", encoding="utf-8")
    run([sys.executable, "generate_download_qr.py"])
    run([sys.executable, "generate_ios_profile.py"])
    encoded = PWA / "downloads" / "wukong-ios-install.mobileconfig.b64.txt"
    profile = PWA / "downloads" / "wukong-ios-install.mobileconfig"
    encoded.write_text(__import__("base64").b64encode(profile.read_bytes()).decode("ascii"), encoding="utf-8")
    run([sys.executable, "sync_wukong_files.py"])


def publish() -> None:
    copy_files(
        [
            "index.html",
            "app.js",
            "shell.js",
            "styles.css",
            "sw.js",
            "install.html",
            "manifest.webmanifest",
            "telegram_status.json",
            "favicon.ico",
            "icons/wukong-180.png",
            "icons/wukong-192.png",
            "icons/wukong-512.png",
            "privacy.html",
            "wukong_file_sync.json",
            "qr/wukong-ios-qr.png",
            "qr/wukong-android-qr.png",
            "qr/download-links.txt",
            "downloads/wukong-ios-install.mobileconfig",
            "downloads/wukong-ios-install.mobileconfig.b64.txt",
            "downloads/wukong-android-release.apk",
        ],
        PWA,
        PUBLISH,
    )
    for stale_download in [
        "downloads/wukong-android-debug.apk",
        "downloads/wukong-ios-signing-kit.zip",
    ]:
        (PUBLISH / stale_download).unlink(missing_ok=True)

    copy_files(
        [
            "generate_download_qr.py",
            "generate_ios_profile.py",
            "sync_wukong_files.py",
            "telegram_wukong_bot.py",
            "wukong_health.py",
            "wukong_self_check.py",
            "wukong_auto_repair.py",
            "wukong_browser_check.js",
            "app.py",
            "start_wukong_telegram.py",
            "stop_wukong_telegram.py",
        ],
        ROOT,
        HERMES_TELEGRAM,
    )
    copy_files(["sync_wukong_files.py"], ROOT, HERMES_PWA)
    copy_files(["start_wukong_pwa.py", "stop_wukong_pwa.py"], ROOT, HERMES_PWA)
    copy_files(["wukong_telegram_runner.sh"], ROOT, HERMES_WUKONG)


def restart_telegram() -> None:
    run([sys.executable, str(HERMES_TELEGRAM / "stop_wukong_telegram.py")], check=False)
    time.sleep(1)
    run([sys.executable, str(HERMES_TELEGRAM / "start_wukong_telegram.py")])
    time.sleep(3)
    run([sys.executable, str(HERMES_TELEGRAM / "telegram_wukong_bot.py"), "--once"], check=False)


def verify() -> None:
    run([sys.executable, "-m", "py_compile", "wukong_auto_repair.py", "wukong_self_check.py", "wukong_health.py"])
    run(["node", "--check", str(PWA / "app.js")])
    run(["node", "--check", str(PWA / "shell.js")])
    run(["node", "--check", "wukong_browser_check.js"])
    run([sys.executable, "wukong_self_check.py", "--public"])
    run(["node", "wukong_browser_check.js"])
    run([sys.executable, "wukong_health.py"])


def main() -> int:
    regenerate()
    publish()
    restart_telegram()
    run([sys.executable, "sync_wukong_files.py"])
    publish()
    verify()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
