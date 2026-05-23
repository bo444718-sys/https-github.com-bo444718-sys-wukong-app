#!/usr/bin/env python3
"""Self-check Wukong release links, cache version, and download inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import plistlib
import re
import struct
import subprocess
import sys
import urllib.error
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PWA = ROOT / "PWA"
HERMES_PWA_ROOT = Path("/Users/wangbo/.hermes/wukong_pwa")
HERMES_PWA = HERMES_PWA_ROOT / "PWA"
HERMES_TELEGRAM = Path("/Users/wangbo/.hermes/wukong_telegram")
MAX_FRESH_SECONDS = 30 * 60
SNAPSHOT_PATHS = [
    ROOT / "wukong_latest_snapshot.json",
    PWA / "wukong_latest_snapshot.json",
    HERMES_PWA / "wukong_latest_snapshot.json",
    HERMES_TELEGRAM / "wukong_latest_snapshot.json",
]
FILE_SYNC_PATHS = [
    ROOT / "wukong_file_sync.json",
    PWA / "wukong_file_sync.json",
    HERMES_PWA_ROOT / "wukong_file_sync.json",
    HERMES_PWA / "wukong_file_sync.json",
    HERMES_TELEGRAM / "wukong_file_sync.json",
]
PUBLIC_URL_PATHS = [
    HERMES_PWA_ROOT / "wukong_pwa_url.txt",
    ROOT / "wukong_pwa_url.txt",
]
NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def app_version() -> str:
    match = re.search(r'APP_VERSION\s*=\s*"(\d+)"', read(PWA / "app.js"))
    if not match:
        raise RuntimeError("PWA/app.js missing APP_VERSION.")
    return match.group(1)


def public_url() -> str:
    for path in PUBLIC_URL_PATHS:
        try:
            value = path.read_text(encoding="utf-8").strip().rstrip("/")
        except OSError:
            continue
        if value.startswith(("https://", "http://")):
            return value
    return ""


def public_url_values() -> dict[Path, str]:
    values: dict[Path, str] = {}
    for path in PUBLIC_URL_PATHS:
        try:
            value = path.read_text(encoding="utf-8").strip().rstrip("/")
        except OSError:
            continue
        if value:
            values[path] = value
    return values


def head_status(url: str) -> int:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "WukongSelfCheck/1.0"})
    try:
        with NO_PROXY_OPENER.open(req, timeout=60) as response:
            return int(response.status)
    except urllib.error.HTTPError:
        raise
    except Exception:
        status, _ = curl_head_info(url)
        return status


def head_info(url: str) -> tuple[int, int]:
    req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "WukongSelfCheck/1.0"})
    try:
        with NO_PROXY_OPENER.open(req, timeout=60) as response:
            length = response.headers.get("Content-Length") or "0"
            return int(response.status), int(length)
    except urllib.error.HTTPError:
        raise
    except Exception:
        return curl_head_info(url)


def get_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "WukongSelfCheck/1.0", "Cache-Control": "no-cache"})
    try:
        with NO_PROXY_OPENER.open(req, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError:
        raise
    except Exception:
        return curl_get_bytes(url)


def public_dns_ip(hostname: str) -> str:
    output = subprocess.check_output(["nslookup", hostname, "1.1.1.1"], text=True, stderr=subprocess.DEVNULL, timeout=12)
    addresses = [line.split("Address:", 1)[1].strip() for line in output.splitlines() if "Address:" in line]
    addresses = [item for item in addresses if re.fullmatch(r"\d+\.\d+\.\d+\.\d+", item) and item != "1.1.1.1"]
    if not addresses:
        raise RuntimeError(f"no public DNS A record for {hostname}")
    return addresses[0]


def curl_resolve_args(url: str) -> list[str]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        return []
    return ["--resolve", f"{parsed.hostname}:443:{public_dns_ip(parsed.hostname)}"]


def curl_head_info(url: str) -> tuple[int, int]:
    output = subprocess.check_output(
        ["curl", "--http1.1", "--retry", "3", "--retry-delay", "2", "-sSI", "--max-time", "60", *curl_resolve_args(url), "-w", "\nCODE=%{http_code}\nCL=%header{content-length}\n", url],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=75,
    )
    status = int(re.search(r"CODE=(\d+)", output).group(1))
    length_match = re.search(r"CL=(\d+)", output)
    return status, int(length_match.group(1)) if length_match else 0


def curl_get_bytes(url: str) -> bytes:
    return subprocess.check_output(
        ["curl", "--http1.1", "--retry", "3", "--retry-delay", "2", "-fsSL", "--max-time", "60", *curl_resolve_args(url), url],
        stderr=subprocess.STDOUT,
        timeout=75,
    )


def get_text(url: str) -> str:
    return get_bytes(url).decode("utf-8", errors="replace")


def get_json(url: str) -> dict:
    return json.loads(get_text(url))


def png_size(data: bytes) -> tuple[int, int]:
    if not data.startswith(b"\x89PNG\r\n\x1a\n") or data[12:16] != b"IHDR":
        return 0, 0
    return struct.unpack(">II", data[16:24])


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


def fresh(value: str, seconds: int = MAX_FRESH_SECONDS) -> bool:
    parsed = parse_time(value)
    if not parsed:
        return False
    age = (datetime.now(timezone.utc) - parsed).total_seconds()
    return 0 <= age <= seconds


def expect(condition: bool, message: str, failures: list[str], passes: list[str]) -> None:
    if condition:
        passes.append(message)
    else:
        failures.append(message)


def check_files(version: str, failures: list[str], passes: list[str]) -> None:
    expected = f"v={version}"
    checks = {
        PWA / "app.js": [f'APP_VERSION = "{version}"'],
        PWA / "shell.js": [f'|| "{version}"', f"sw.js?v=${{WUKONG_SHELL_VERSION}}"],
        PWA / "sw.js": [f"wukong-pwa-v{version}", "./exchange_markets.json"],
        PWA / "index.html": [
            f"app.js?{expected}",
            f"install.html?{expected}",
            f"privacy.html?{expected}",
            f'<span id="releaseVersion">v{version}</span>',
            f'<strong id="appVersion">v{version}</strong>',
            f'<strong id="releaseGuard">v{version}</strong>',
            f'<strong id="opsMatrixVersion">v{version}</strong>',
        ],
        PWA / "install.html": [f"shell.js?{expected}", f"privacy.html?{expected}", f"wukong-android-release.apk?{expected}"],
        PWA / "privacy.html": [f"shell.js?{expected}", f"index.html?{expected}"],
        PWA / "manifest.webmanifest": [f"index.html?{expected}", f"install.html?{expected}"],
        ROOT / "generate_download_qr.py": [expected],
        ROOT / "generate_ios_profile.py": [expected],
        ROOT / "telegram_wukong_bot.py": [f'PWA_VERSION = "{version}"'],
        ROOT / "wukong_health.py": [f'PWA_VERSION = "{version}"', "iPhone安装访问", "Android下载访问"],
        ROOT / "ANDROID_IOS_DOWNLOAD.md": [expected],
        ROOT / "PWA_INSTALL.md": [expected],
        ROOT / "README.md": [f"wukong-android-release.apk?{expected}"],
    }
    for path, needles in checks.items():
        text = read(path)
        for needle in needles:
            expect(needle in text, f"{path.relative_to(ROOT)} contains {needle}", failures, passes)


def check_generated(version: str, failures: list[str], passes: list[str]) -> None:
    links = read(PWA / "qr" / "download-links.txt")
    expect(f"install.html?v={version}" in links, "QR links use current iPhone install URL", failures, passes)
    expect(f"wukong-android-release.apk?v={version}" in links, "QR links use current Android APK URL", failures, passes)

    with (PWA / "downloads" / "wukong-ios-install.mobileconfig").open("rb") as handle:
        profile = plistlib.load(handle)
    webclip_url = profile["PayloadContent"][0]["URL"]
    expect(webclip_url.endswith(f"/index.html?v={version}"), "iPhone profile WebClip URL uses current version", failures, passes)

    icon_dimensions = {
        PWA / "icons" / "wukong-180.png": (180, 180),
        PWA / "icons" / "wukong-192.png": (192, 192),
        PWA / "icons" / "wukong-512.png": (512, 512),
    }
    for path, expected_size in icon_dimensions.items():
        expect(png_size(path.read_bytes()) == expected_size, f"{path.relative_to(ROOT)} PNG dimensions are {expected_size[0]}x{expected_size[1]}", failures, passes)
    for path in [PWA / "qr" / "wukong-ios-qr.png", PWA / "qr" / "wukong-android-qr.png"]:
        width, height = png_size(path.read_bytes())
        expect(width == height and width >= 420, f"{path.relative_to(ROOT)} QR PNG is square and high resolution", failures, passes)
    expect((PWA / "downloads" / "wukong-android-release.apk").read_bytes()[:2] == b"PK", "Android release APK is a zip package", failures, passes)

    for path in FILE_SYNC_PATHS:
        if not path.exists():
            failures.append(f"{path} file sync inventory exists")
            continue
        try:
            inventory = json.loads(read(path))
        except Exception as exc:
            failures.append(f"{path} file sync inventory is readable JSON: {exc}")
            continue
        paths = [item["path"] for item in inventory.get("files", [])]
        apks = [path for path in paths if path.endswith(".apk")]
        logs = [path for path in paths if path.endswith(".log")]
        zips = [path for path in paths if path.endswith(".zip")]
        expect(apks == ["PWA/downloads/wukong-android-release.apk"], f"{path} exposes only release APK", failures, passes)
        expect(not logs, f"{path} excludes logs", failures, passes)
        expect(not zips, f"{path} excludes signing and archive packages", failures, passes)
        expect(fresh(str(inventory.get("generatedAt", ""))), f"{path} file sync inventory is fresh", failures, passes)

    for path in SNAPSHOT_PATHS:
        if not path.exists():
            failures.append(f"{path} latest snapshot exists")
            continue
        try:
            snapshot = json.loads(read(path))
        except Exception as exc:
            failures.append(f"{path} snapshot is readable JSON: {exc}")
            continue
        install_line = next((line for line in (snapshot.get("summary") or "").splitlines() if line.startswith("iPhone安装：")), "")
        expect(f"install.html?v={version}" in install_line, f"{path} snapshot install link uses current version", failures, passes)
        expect(fresh(str(snapshot.get("updatedAt", ""))), f"{path} latest snapshot is fresh", failures, passes)

    exchange_paths = [
        ROOT / "exchange_markets.json",
        PWA / "exchange_markets.json",
        HERMES_PWA / "exchange_markets.json",
        HERMES_TELEGRAM / "exchange_markets.json",
    ]
    for path in exchange_paths:
        if not path.exists():
            failures.append(f"{path} exchange API snapshot exists")
            continue
        try:
            snapshot = json.loads(read(path))
        except Exception as exc:
            failures.append(f"{path} exchange API snapshot is readable JSON: {exc}")
            continue
        venues = snapshot.get("venues") or {}
        expect(all(name in venues for name in ["binance", "okx", "gate"]), f"{path} contains Binance OKX Gate venues", failures, passes)
        expect(len(snapshot.get("markets") or []) >= 4, f"{path} contains tracked exchange markets", failures, passes)
        expect(fresh(str(snapshot.get("generatedAt", ""))), f"{path} exchange API snapshot is fresh", failures, passes)


def check_runtime_publish(failures: list[str], passes: list[str]) -> None:
    pwa_files = [
        "index.html",
        "app.js",
        "shell.js",
        "styles.css",
        "sw.js",
        "install.html",
        "privacy.html",
        "manifest.webmanifest",
        "favicon.ico",
        "icons/wukong-180.png",
        "icons/wukong-192.png",
        "icons/wukong-512.png",
        "wukong_file_sync.json",
        "exchange_markets.json",
        "gate_markets.json",
        "qr/download-links.txt",
        "qr/wukong-ios-qr.png",
        "qr/wukong-android-qr.png",
        "downloads/wukong-ios-install.mobileconfig",
        "downloads/wukong-ios-install.mobileconfig.b64.txt",
        "downloads/wukong-android-release.apk",
    ]
    for rel in pwa_files:
        source = PWA / rel
        target = HERMES_PWA / rel
        exists = target.exists()
        expect(exists, f"published PWA has {rel}", failures, passes)
        if exists and rel not in {"exchange_markets.json", "gate_markets.json"}:
            expect(digest(source) == digest(target), f"published PWA {rel} matches local", failures, passes)

    telegram_files = [
        "telegram_wukong_bot.py",
        "wukong_health.py",
        "wukong_self_check.py",
        "wukong_auto_repair.py",
        "wukong_browser_check.js",
        "sync_wukong_files.py",
        "generate_download_qr.py",
        "generate_ios_profile.py",
        "sync_exchange_api.py",
    ]
    for rel in telegram_files:
        source = ROOT / rel
        target = HERMES_TELEGRAM / rel
        exists = target.exists()
        expect(exists, f"Telegram runtime has {rel}", failures, passes)
        if exists:
            expect(digest(source) == digest(target), f"Telegram runtime {rel} matches local", failures, passes)


def check_public(version: str, failures: list[str], passes: list[str]) -> None:
    base = public_url()
    expect(bool(base), "public PWA URL is configured", failures, passes)
    if not base:
        return
    configured_urls = public_url_values()
    for path, value in configured_urls.items():
        expect(value == base, f"{path} matches active public PWA URL", failures, passes)
    paths = [
        f"/index.html?v={version}",
        f"/install.html?v={version}",
        f"/privacy.html?v={version}",
        f"/app.js?v={version}",
        f"/shell.js?v={version}",
        f"/styles.css?v={version}",
        f"/manifest.webmanifest?v={version}",
        f"/favicon.ico?v={version}",
        f"/icons/wukong-180.png?v={version}",
        f"/icons/wukong-192.png?v={version}",
        f"/icons/wukong-512.png?v={version}",
        f"/sw.js?v={version}",
        f"/wukong_latest_snapshot.json?v={version}",
        f"/exchange_markets.json?v={version}",
        f"/wukong_file_sync.json?v={version}",
        f"/qr/download-links.txt?v={version}",
        f"/qr/wukong-ios-qr.png?v={version}",
        f"/qr/wukong-android-qr.png?v={version}",
        f"/downloads/wukong-ios-install.mobileconfig?v={version}",
        f"/downloads/wukong-android-release.apk?v={version}",
    ]
    for path in paths:
        try:
            status = head_status(base + path)
        except Exception as exc:
            failures.append(f"public {path} is reachable: {exc}")
            continue
        expect(status == 200, f"public {path} returns HTTP 200", failures, passes)

    content_checks = {
        f"/index.html?v={version}": [f'<span id="releaseVersion">v{version}</span>', f"app.js?v={version}"],
        f"/install.html?v={version}": [f"shell.js?v={version}", f"privacy.html?v={version}", f"wukong-android-release.apk?v={version}", "iPhone 安装文件"],
        f"/app.js?v={version}": [f'APP_VERSION = "{version}"', f"sw.js?v=${{APP_VERSION}}"],
        f"/shell.js?v={version}": [f'|| "{version}"', f"sw.js?v=${{WUKONG_SHELL_VERSION}}"],
        f"/sw.js?v={version}": [f"wukong-pwa-v{version}", "./exchange_markets.json"],
        f"/manifest.webmanifest?v={version}": [f"index.html?v={version}", f"install.html?v={version}", "icons/wukong-192.png", "icons/wukong-512.png"],
        f"/qr/download-links.txt?v={version}": [f"install.html?v={version}", f"wukong-android-release.apk?v={version}"],
    }
    for path, needles in content_checks.items():
        try:
            text = get_text(base + path)
        except Exception as exc:
            failures.append(f"public {path} content is readable: {exc}")
            continue
        for needle in needles:
            expect(needle in text, f"public {path} contains {needle}", failures, passes)

    try:
        profile = plistlib.loads(get_bytes(base + f"/downloads/wukong-ios-install.mobileconfig?v={version}"))
        webclip_url = profile["PayloadContent"][0]["URL"]
        expect(webclip_url.endswith(f"/index.html?v={version}"), "public iPhone profile WebClip URL uses current version", failures, passes)
    except Exception as exc:
        failures.append(f"public iPhone profile is readable plist: {exc}")

    public_binary_matches = [
        ("/favicon.ico", PWA / "favicon.ico"),
        ("/icons/wukong-180.png", PWA / "icons" / "wukong-180.png"),
        ("/icons/wukong-192.png", PWA / "icons" / "wukong-192.png"),
        ("/icons/wukong-512.png", PWA / "icons" / "wukong-512.png"),
        ("/qr/wukong-ios-qr.png", PWA / "qr" / "wukong-ios-qr.png"),
        ("/qr/wukong-android-qr.png", PWA / "qr" / "wukong-android-qr.png"),
        ("/downloads/wukong-ios-install.mobileconfig", PWA / "downloads" / "wukong-ios-install.mobileconfig"),
    ]
    for url_path, source in public_binary_matches:
        try:
            public_bytes = get_bytes(base + f"{url_path}?v={version}")
        except Exception as exc:
            failures.append(f"public {url_path} bytes are readable: {exc}")
            continue
        expect(hashlib.sha256(public_bytes).hexdigest() == digest(source), f"public {url_path} bytes match local", failures, passes)
    try:
        status, content_length = head_info(base + f"/downloads/wukong-android-release.apk?v={version}")
        expect(status == 200, "public Android APK HEAD returns HTTP 200 for integrity", failures, passes)
        expect(content_length == (PWA / "downloads" / "wukong-android-release.apk").stat().st_size, "public Android APK content length matches local", failures, passes)
    except Exception as exc:
        failures.append(f"public Android APK integrity headers are readable: {exc}")

    try:
        snapshot = get_json(base + f"/wukong_latest_snapshot.json?v={version}")
        install_line = next((line for line in (snapshot.get("summary") or "").splitlines() if line.startswith("iPhone安装：")), "")
        expect(f"install.html?v={version}" in install_line, "public snapshot install link uses current version", failures, passes)
        expect(fresh(str(snapshot.get("updatedAt", ""))), "public snapshot is fresh", failures, passes)
    except Exception as exc:
        failures.append(f"public latest snapshot is readable JSON: {exc}")

    try:
        snapshot = get_json(base + f"/exchange_markets.json?v={version}")
        venues = snapshot.get("venues") or {}
        expect(all(name in venues for name in ["binance", "okx", "gate"]), "public exchange API snapshot contains Binance OKX Gate", failures, passes)
        expect(len(snapshot.get("markets") or []) >= 4, "public exchange API snapshot contains tracked markets", failures, passes)
        expect(fresh(str(snapshot.get("generatedAt", ""))), "public exchange API snapshot is fresh", failures, passes)
    except Exception as exc:
        failures.append(f"public exchange API snapshot is readable JSON: {exc}")

    try:
        inventory = get_json(base + f"/wukong_file_sync.json?v={version}")
        paths = [item["path"] for item in inventory.get("files", [])]
        apks = [path for path in paths if path.endswith(".apk")]
        logs = [path for path in paths if path.endswith(".log")]
        zips = [path for path in paths if path.endswith(".zip")]
        expect(apks == ["PWA/downloads/wukong-android-release.apk"], "public file sync exposes only release APK", failures, passes)
        expect(not logs, "public file sync excludes logs", failures, passes)
        expect(not zips, "public file sync excludes signing and archive packages", failures, passes)
        expect(fresh(str(inventory.get("generatedAt", ""))), "public file sync inventory is fresh", failures, passes)
    except Exception as exc:
        failures.append(f"public file sync inventory is readable JSON: {exc}")

    try:
        status = head_status(base + "/downloads/wukong-android-debug.apk")
        expect(status == 404, "public debug APK is not exposed", failures, passes)
    except urllib.error.HTTPError as exc:
        expect(exc.code == 404, "public debug APK is not exposed", failures, passes)
    except Exception as exc:
        failures.append(f"public debug APK check failed: {exc}")
    try:
        status = head_status(base + "/downloads/wukong-ios-signing-kit.zip")
        expect(status == 404, "public iOS signing kit is not exposed", failures, passes)
    except urllib.error.HTTPError as exc:
        expect(exc.code == 404, "public iOS signing kit is not exposed", failures, passes)
    except Exception as exc:
        failures.append(f"public iOS signing kit check failed: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Wukong self-checks.")
    parser.add_argument("--public", action="store_true", help="Also check the public Cloudflare download URLs.")
    args = parser.parse_args()
    version = app_version()
    failures: list[str] = []
    passes: list[str] = []

    check_files(version, failures, passes)
    check_generated(version, failures, passes)
    check_runtime_publish(failures, passes)
    if args.public:
        check_public(version, failures, passes)

    print(f"悟空自检 v{version}")
    print(f"通过：{len(passes)}")
    if failures:
        print(f"失败：{len(failures)}")
        for item in failures:
            print(f"- {item}")
        return 1
    print("失败：0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
