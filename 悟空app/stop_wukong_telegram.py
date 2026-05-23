#!/usr/bin/env python3
"""Stop the background Wukong Telegram push process."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PID_PATH = ROOT / ".wukong_telegram_bot.pid"


def main() -> int:
    try:
        pid = int(PID_PATH.read_text(encoding="utf-8").strip())
    except Exception:
        print("No Wukong Telegram pid file found.")
        return 0

    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        print(f"Wukong Telegram process is not running: pid {pid}")
        PID_PATH.unlink(missing_ok=True)
        return 0

    for _ in range(30):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            PID_PATH.unlink(missing_ok=True)
            print(f"Stopped Wukong Telegram push: pid {pid}")
            return 0
        time.sleep(0.2)

    print(f"Sent SIGTERM to Wukong Telegram push: pid {pid}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
