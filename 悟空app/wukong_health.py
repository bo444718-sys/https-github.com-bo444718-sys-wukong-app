#!/usr/bin/env python3
"""Health report for Wukong PWA, Telegram push, and live data snapshots."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
HERMES = Path("/Users/wangbo/.hermes")
PWA_VERSION = "122"
MAX_FRESH_SECONDS = 30 * 60
PWA_URL_PATHS = [HERMES / "wukong_pwa" / "wukong_pwa_url.txt", ROOT / "wukong_pwa_url.txt"]
SNAPSHOT_PATHS = [HERMES / "wukong_telegram" / "wukong_latest_snapshot.json", ROOT / "wukong_latest_snapshot.json"]
FILE_SYNC_PATHS = [HERMES / "wukong_telegram" / "wukong_file_sync.json", HERMES / "wukong_pwa" / "wukong_file_sync.json", ROOT / "wukong_file_sync.json"]
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def run_text(args: list[str]) -> str:
    try:
        return subprocess.check_output(args, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def pgrep(pattern: str) -> list[str]:
    output = run_text(["pgrep", "-fl", pattern])
    ignored = ("wukong_health.py", "pgrep -fl", "rg '", "grep ")
    return [line for line in output.splitlines() if line.strip() and not any(item in line for item in ignored)]


def launch_status(label: str) -> str:
    output = run_text(["launchctl", "list"])
    for line in output.splitlines():
        if line.endswith(label) or f"\t{label}" in line:
            parts = line.split()
            if len(parts) >= 3:
                return f"loaded status={parts[1]} pid={parts[0]}"
            return "loaded"
    return "not loaded"


def read_first(paths: list[Path]) -> str:
    for path in paths:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if value:
            return value
    return ""


def head_status(url: str) -> str:
    if not url:
        return "missing"
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "WukongHealth/1.0"})
        with NO_PROXY_OPENER.open(req, timeout=12) as response:
            return f"HTTP {response.status}"
    except Exception as exc:
        return f"down: {exc}"


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def freshness_label(value: str) -> str:
    parsed = parse_time(value)
    if not parsed:
        return "missing"
    age = max(0, int((datetime.now(timezone.utc) - parsed).total_seconds()))
    if age < 60:
        text = f"{age}秒前"
    else:
        text = f"{age // 60}分钟前"
    return f"正常 {text}" if age <= MAX_FRESH_SECONDS else f"过期 {text}"


def snapshot_info() -> tuple[str, str, str]:
    for path in SNAPSHOT_PATHS:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        updated = payload.get("updatedAt") or ""
        generated = payload.get("sourceGeneratedAt") or ""
        summary = payload.get("summary") or ""
        install_line = ""
        for line in summary.splitlines():
            if line.startswith("iPhone安装："):
                install_line = line.replace("iPhone安装：", "", 1).strip()
                break
        return updated, generated, install_line
    return "", "", ""


def file_sync_info() -> tuple[int, str]:
    for path in FILE_SYNC_PATHS:
        if not path.exists():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return int(payload.get("fileCount", 0)), str(payload.get("generatedAt", ""))
        except Exception:
            continue
    return 0, ""


def versioned_install_url(pwa_url: str) -> str:
    base = pwa_url.rstrip("/")
    return f"{base}/install.html?v={PWA_VERSION}" if base else ""


def normalize_install_url(value: str, pwa_url: str) -> str:
    if not value:
        return ""
    if "install.html" in value:
        if pwa_url:
            return versioned_install_url(pwa_url)
        return f"{value.split('install.html', 1)[0]}install.html?v={PWA_VERSION}"
    base = pwa_url.rstrip("/") or value.rstrip("/")
    return f"{base}/install.html?v={PWA_VERSION}" if base.startswith("http") else value


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        if "=" not in raw or raw.strip().startswith("#"):
            continue
        key, value = raw.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def discover_chat_id() -> str:
    try:
        channels = json.loads((HERMES / "channel_directory.json").read_text(encoding="utf-8"))["platforms"]["telegram"]
        return str(channels[0]["id"])
    except Exception:
        return ""


def send_telegram(text: str) -> None:
    env = load_env(HERMES / ".env")
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "") or discover_chat_id()
    if not token or not chat_id:
        raise SystemExit("Telegram token or chat id is missing.")
    payload = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}, ensure_ascii=False).encode()
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        response.read()


def self_check_status(*extra_args: str, timeout: int = 25) -> str:
    script = ROOT / "wukong_self_check.py"
    if not script.exists():
        return "missing"
    try:
        result = subprocess.run(
            [sys.executable, str(script), *extra_args],
            cwd=str(ROOT),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
        )
    except Exception as exc:
        return f"failed: {exc}"
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    summary = " / ".join(lines[-2:]) if len(lines) >= 2 else (lines[0] if lines else "no output")
    return f"OK {summary}" if result.returncode == 0 else f"FAIL {summary}"


def build_report() -> str:
    pwa_url = read_first(PWA_URL_PATHS)
    install_url = versioned_install_url(pwa_url)
    android_url = f"{pwa_url.rstrip('/')}/downloads/wukong-android-release.apk?v={PWA_VERSION}" if pwa_url else ""
    updated, generated, snapshot_url = snapshot_info()
    snapshot_install_url = normalize_install_url(snapshot_url, pwa_url)
    file_count, file_generated = file_sync_info()
    pwa_processes = pgrep(r"wukong_pwa_server.py|http.server 8088|cloudflared tunnel")
    telegram_processes = pgrep("telegram_wukong_bot.py")
    app_processes = pgrep(r"Wukong.app/Contents/MacOS/Wukong")
    lines = [
        "悟空健康状态",
        f"检查时间：{datetime.now().strftime('%m-%d %H:%M:%S')}",
        "",
        f"悟空App：{len(app_processes)} 个进程",
        "",
        f"PWA链接：{pwa_url or '--'}",
        f"iPhone安装：{install_url or '--'}",
        f"Android下载：{android_url or '--'}",
        f"PWA访问：{head_status(pwa_url)}",
        f"iPhone安装访问：{head_status(install_url)}",
        f"Android下载访问：{head_status(android_url)}",
        f"PWA服务：{len(pwa_processes)} 个进程",
        f"PWA自愈：{launch_status('ai.wukong.pwa')}",
        "",
        f"Telegram推送：{len(telegram_processes)} 个进程",
        f"Telegram自愈：{launch_status('ai.wukong.telegram')}",
        "",
        f"快照更新：{updated or '--'}",
        f"快照新鲜度：{freshness_label(updated)}",
        f"行情生成：{generated or '--'}",
        f"摘要安装链接：{snapshot_install_url or '--'}",
        "",
        f"文件同步：{file_count} 个文件",
        f"文件清单：{file_generated or '--'}",
        f"文件新鲜度：{freshness_label(file_generated)}",
        "",
        f"深度自检：{self_check_status()}",
        f"公网自检：{self_check_status('--public', timeout=180)}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Wukong health.")
    parser.add_argument("--send-telegram", action="store_true", help="Send the health report to Telegram.")
    args = parser.parse_args()
    report = build_report()
    print(report)
    if args.send_telegram:
        send_telegram(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
