#!/usr/bin/env python3
"""Stop Wukong PWA server and Cloudflare quick tunnel."""

from __future__ import annotations

import json
import os
import signal
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PID_PATH = ROOT / ".wukong_pwa.pid.json"


def main() -> int:
    try:
        pids = json.loads(PID_PATH.read_text(encoding="utf-8"))
    except Exception:
        print("No Wukong PWA pid file found.")
        return 0

    for name, raw_pid in pids.items():
        try:
            pid = int(raw_pid)
            os.kill(pid, signal.SIGTERM)
            print(f"Stopped {name}: pid {pid}")
        except ProcessLookupError:
            print(f"{name} was not running: pid {raw_pid}")
        except Exception as exc:
            print(f"Could not stop {name}: {exc}")
    PID_PATH.unlink(missing_ok=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
