#!/usr/bin/env python3
"""Start the Wukong PWA server and a Cloudflare quick tunnel."""

from __future__ import annotations

import json
import ipaddress
import os
import re
import signal
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PWA_ROOT = ROOT / "PWA"
PID_PATH = ROOT / ".wukong_pwa.pid.json"
LOG_PATH = ROOT / "wukong_pwa_tunnel.log"
URL_PATH = ROOT / "wukong_pwa_url.txt"
PENDING_URL_PATH = ROOT / ".wukong_pwa_pending_url"
LAST_SENT_URL_PATH = ROOT / ".wukong_pwa_last_sent_url"
PORT = int(os.getenv("WUKONG_PWA_PORT", "8088"))
CLOUDFLARED = os.getenv("CLOUDFLARED_BIN") or shutil.which("cloudflared") or "/opt/homebrew/bin/cloudflared"


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def load_pids() -> dict[str, int]:
    try:
        payload = json.loads(PID_PATH.read_text(encoding="utf-8"))
        return {key: int(value) for key, value in payload.items()}
    except Exception:
        return {}


def start_process(args: list[str], *, cwd: Path, log: Path | None = None) -> subprocess.Popen[bytes]:
    stdout = log.open("ab") if log else subprocess.DEVNULL
    stderr = subprocess.STDOUT if log else subprocess.DEVNULL
    return subprocess.Popen(
        args,
        cwd=str(cwd),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )


def listening_pid(port: int) -> int | None:
    try:
        output = subprocess.check_output(
            ["lsof", "-tiTCP:%d" % port, "-sTCP:LISTEN"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        for line in output.splitlines():
            if line.strip().isdigit():
                return int(line.strip())
    except Exception:
        return None
    return None


def matching_pid(pattern: str) -> int | None:
    try:
        output = subprocess.check_output(["pgrep", "-f", pattern], text=True, stderr=subprocess.DEVNULL)
        own_pid = os.getpid()
        for line in output.splitlines():
            if line.strip().isdigit():
                pid = int(line.strip())
                if pid != own_pid:
                    return pid
    except Exception:
        return None
    return None


def ensure_server(pids: dict[str, int]) -> int:
    existing = pids.get("server")
    if existing and pid_running(existing):
        return existing
    active = listening_pid(PORT)
    if active:
        return active
    process = start_process([sys.executable, str(ROOT / "wukong_pwa_server.py")], cwd=ROOT)
    return process.pid


def sync_files() -> None:
    script = ROOT / "sync_wukong_files.py"
    if script.exists():
        subprocess.run([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)


def ensure_tunnel(pids: dict[str, int]) -> int:
    existing = pids.get("tunnel")
    if existing and pid_running(existing):
        return existing
    active = matching_pid(r"cloudflared tunnel .*--url http://127\.0\.0\.1:%d" % PORT)
    if active:
        return active
    LOG_PATH.write_text("", encoding="utf-8")
    process = start_process(
        [CLOUDFLARED, "tunnel", "--protocol", "http2", "--url", f"http://127.0.0.1:{PORT}"],
        cwd=PWA_ROOT,
        log=LOG_PATH,
    )
    return process.pid


def stop_pid(pid: int | None) -> None:
    if not pid:
        return
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        return


def public_dns_ip(hostname: str) -> str:
    output = subprocess.check_output(
        ["nslookup", hostname, "1.1.1.1"],
        text=True,
        stderr=subprocess.DEVNULL,
        timeout=12,
    )
    addresses = []
    for line in output.splitlines():
        if not line.startswith("Address:"):
            continue
        value = line.split(":", 1)[1].strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+\.\d+", value):
            continue
        parsed = ipaddress.ip_address(value)
        if parsed.is_private or parsed.is_loopback or parsed.is_link_local or value.startswith("198.18.") or value.startswith("198.19."):
            continue
        addresses.append(value)
    if not addresses:
        raise RuntimeError(f"Public DNS did not resolve {hostname}")
    return addresses[0]


def curl_head_status(url: str) -> int:
    parsed = urllib.parse.urlparse(url)
    resolve_args: list[str] = []
    if parsed.scheme == "https" and parsed.hostname:
        resolve_args = ["--resolve", f"{parsed.hostname}:443:{public_dns_ip(parsed.hostname)}"]
    output = subprocess.check_output(
        [
            "curl",
            "--http1.1",
            "--retry",
            "2",
            "--retry-delay",
            "2",
            "-sSI",
            "--max-time",
            "20",
            *resolve_args,
            "-w",
            "\nCODE=%{http_code}\n",
            url,
        ],
        text=True,
        stderr=subprocess.STDOUT,
        timeout=35,
    )
    match = re.search(r"CODE=(\d+)", output)
    return int(match.group(1)) if match else 0


def url_is_healthy(url: str) -> bool:
    if not url:
        return False
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "WukongPWAHealth/1.0"})
        with urllib.request.urlopen(req, timeout=12) as response:
            return 200 <= response.status < 400
    except Exception:
        try:
            return 200 <= curl_head_status(url) < 400
        except Exception:
            return False


def current_url() -> str:
    try:
        return URL_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def pending_url() -> str:
    try:
        return PENDING_URL_PATH.read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def ensure_healthy_tunnel(pids: dict[str, int]) -> tuple[int, str, bool]:
    pending = pending_url()
    if pending and url_is_healthy(pending):
        URL_PATH.write_text(pending + "\n", encoding="utf-8")
        PENDING_URL_PATH.unlink(missing_ok=True)
        existing_pid = pids.get("tunnel")
        active = matching_pid(r"cloudflared tunnel .*--url http://127\.0\.0\.1:%d" % PORT)
        return active or existing_pid or ensure_tunnel(pids), pending, False

    existing_url = current_url()
    existing_pid = pids.get("tunnel")
    if existing_pid and pid_running(existing_pid) and url_is_healthy(existing_url):
        return existing_pid, existing_url, False
    active = matching_pid(r"cloudflared tunnel .*--url http://127\.0\.0\.1:%d" % PORT)
    if active and active != existing_pid and url_is_healthy(existing_url):
        return active, existing_url, False

    stop_pid(existing_pid)
    if active and active != existing_pid:
        stop_pid(active)

    LOG_PATH.write_text("", encoding="utf-8")
    process = start_process(
        [CLOUDFLARED, "tunnel", "--protocol", "http2", "--url", f"http://127.0.0.1:{PORT}"],
        cwd=PWA_ROOT,
        log=LOG_PATH,
    )
    url = wait_for_url()
    deadline = time.time() + 180
    healthy = False
    while url and time.time() < deadline:
        if url_is_healthy(url):
            healthy = True
            break
        time.sleep(3)
    if healthy:
        URL_PATH.write_text(url + "\n", encoding="utf-8")
        PENDING_URL_PATH.unlink(missing_ok=True)
        return process.pid, url, True
    if url:
        PENDING_URL_PATH.write_text(url + "\n", encoding="utf-8")
    return process.pid, existing_url, True


def wait_for_url(timeout: int = 45) -> str:
    pattern = re.compile(r"https://[-a-z0-9]+\.trycloudflare\.com")
    deadline = time.time() + timeout
    while time.time() < deadline:
        if LOG_PATH.exists():
            match = pattern.search(LOG_PATH.read_text(encoding="utf-8", errors="replace"))
            if match:
                return match.group(0)
        time.sleep(1)
    return ""


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
    path = Path("/Users/wangbo/.hermes/channel_directory.json")
    try:
        channels = json.loads(path.read_text(encoding="utf-8"))["platforms"]["telegram"]
        return str(channels[0]["id"])
    except Exception:
        return ""


def send_telegram(url: str) -> None:
    env = load_env(Path("/Users/wangbo/.hermes/.env"))
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "") or discover_chat_id()
    if not token or not chat_id or not url:
        return
    if LAST_SENT_URL_PATH.exists() and LAST_SENT_URL_PATH.read_text(encoding="utf-8").strip() == url:
        return
    text = (
        "悟空 iPhone 安装链接已更新：\n"
        f"{url}\n\n"
        "在 iPhone Safari 打开，分享按钮 -> 添加到主屏幕，名称填写“悟空”。"
    )
    payload = json.dumps(
        {"chat_id": chat_id, "text": text, "disable_web_page_preview": False},
        ensure_ascii=False,
    ).encode("utf-8")
    endpoint = f"https://api.telegram.org/bot{token}/sendMessage"
    req = urllib.request.Request(endpoint, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
    except Exception:
        proxy = os.getenv("HTTPS_PROXY") or os.getenv("HTTP_PROXY") or "http://127.0.0.1:7892"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
        with opener.open(req, timeout=20) as response:
            response.read()
    LAST_SENT_URL_PATH.write_text(url + "\n", encoding="utf-8")


def main() -> int:
    sync_files()
    pids = load_pids()
    server_pid = ensure_server(pids)
    tunnel_pid, url, recreated = ensure_healthy_tunnel(pids)
    PID_PATH.write_text(json.dumps({"server": server_pid, "tunnel": tunnel_pid}, indent=2), encoding="utf-8")
    if url:
        try:
            send_telegram(url)
        except Exception as exc:
            print(f"Wukong PWA Telegram notification skipped: {exc}")
        status = "recreated" if recreated else "healthy"
        print(f"Wukong PWA is {status}: {url}")
    else:
        print("Wukong PWA server is running, but no Cloudflare tunnel URL was detected yet.")
    print(f"server pid: {server_pid}")
    print(f"tunnel pid: {tunnel_pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
