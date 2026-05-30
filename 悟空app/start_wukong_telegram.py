#!/usr/bin/env python3
"""Start Wukong Telegram push mode as a background process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PID_PATH = ROOT / ".wukong_telegram_bot.pid"
LOG_PATH = ROOT / "wukong_telegram_bot.log"
ERROR_LOG_PATH = ROOT / "wukong_telegram_bot.error.log"


def pid_is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def read_pid() -> int | None:
    try:
        return int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def main() -> int:
    existing_pid = read_pid()
    if existing_pid and pid_is_running(existing_pid):
        print(f"Wukong Telegram push is already running: pid {existing_pid}")
        return 0

    python = sys.executable or "/usr/bin/python3"
    stdout = LOG_PATH.open("ab")
    stderr = ERROR_LOG_PATH.open("ab")
    process = subprocess.Popen(
        [python, str(ROOT / "telegram_wukong_bot.py"), "--push-only", "--interval", "300"],
        cwd=str(ROOT),
        stdin=subprocess.DEVNULL,
        stdout=stdout,
        stderr=stderr,
        start_new_session=True,
    )
    PID_PATH.write_text(f"{process.pid}\n", encoding="utf-8")
    print(f"Started Wukong Telegram push: pid {process.pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
