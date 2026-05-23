#!/usr/bin/env python3
"""Create a professional readiness report for the Wukong trading system."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUTPUT_PATHS = [
    ROOT / "PWA" / "professional_trade_system.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/professional_trade_system.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/professional_trade_system.json"),
]
EXCLUDE_PARTS = {
    "node_modules",
    ".gradle",
    "build",
    ".git",
    ".build",
    ".build-appstore-check",
    ".build-cache",
    ".pycache",
    ".pycache-check",
    ".playwright-cli",
    "__pycache__",
}
EXCLUDE_SUFFIXES = {".swp", ".log", ".pid", ".tmp"}


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return default


def scan_files() -> list[str]:
    rows = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDE_PARTS for part in path.relative_to(ROOT).parts):
            continue
        if path.name == ".DS_Store" or path.suffix in EXCLUDE_SUFFIXES:
            continue
        rows.append(str(path.relative_to(ROOT)))
    return sorted(rows)


def exists(path: str) -> bool:
    return (ROOT / path).exists()


def module(name: str, ready: bool, state: str, detail: str) -> dict[str, Any]:
    return {"name": name, "ready": ready, "state": state, "detail": detail}


def main() -> int:
    files = scan_files()
    private_status = load_json(ROOT / "PWA" / "gate_private_status.json", {})
    preflight = load_json(ROOT / "PWA" / "gate_trade_preflight.json", {})
    paper = load_json(ROOT / "PWA" / "paper_trading_state.json", {})
    exchange = load_json(ROOT / "PWA" / "exchange_markets.json", {})
    telegram = load_json(ROOT / "PWA" / "telegram_status.json", {})
    file_sync = load_json(ROOT / "PWA" / "wukong_file_sync.json", {})

    blockers = preflight.get("blockers") or []
    modules = [
        module("市场数据", bool(exchange.get("markets")), "ready" if exchange.get("markets") else "waiting", "Binance / OKX / Gate 公开行情快照"),
        module("信号引擎", bool((preflight.get("signalTradeGate") or {}).get("queue")), (preflight.get("signalTradeGate") or {}).get("state", "waiting"), (preflight.get("signalTradeGate") or {}).get("reason", "等待信号")),
        module("自动纸交易", paper.get("state") == "running", paper.get("state", "waiting"), paper.get("reason", "等待纸交易引擎")),
        module("Gate 私有 API", bool(private_status.get("authenticated")), "authenticated" if private_status.get("authenticated") else "waiting", private_status.get("message", "等待验证")),
        module("风控预算", bool((preflight.get("riskBudget") or {}).get("maxNotionalUsdt")), "ready", "100U / 10X / 5U 保证金 / 50U 名义仓位"),
        module("Telegram 控制台", bool(telegram.get("status")), telegram.get("status", "waiting"), "支持 /paper 与 /confirm_live"),
        module("文件同步", bool(file_sync.get("fileCount")), "ready" if file_sync.get("fileCount") else "waiting", f"{file_sync.get('fileCount', len(files))} 文件"),
        module("实盘 API 提交", False, "locked", "订单端点关闭；只允许预检和人工确认流程"),
    ]

    payload = {
        "app": "悟空",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "profile": "professional-auto-trading-framework",
        "fileScan": {
            "count": len(files),
            "requiredReady": all(
                exists(path)
                for path in [
                    "PWA/index.html",
                    "PWA/app.js",
                    "PWA/styles.css",
                    "gate_private_status.py",
                    "gate_trade_preflight.py",
                    "wukong_paper_engine.py",
                    "telegram_wukong_bot.py",
                    "sync_exchange_api.py",
                ]
            ),
        },
        "executionModes": [
            {"name": "auto-paper", "enabled": True, "detail": "信号出现自动纸交易，信号消失自动关闭"},
            {"name": "telegram-confirm-preflight", "enabled": True, "detail": "Telegram 一键确认只做预检，不提交订单"},
            {"name": "live-api-ready-shell", "enabled": True, "detail": "Gate 私有 API 已可读，实盘提交端点保持锁定"},
            {"name": "unattended-live-order", "enabled": False, "detail": "无人值守实盘自动下单关闭"},
        ],
        "modules": modules,
        "liveReadiness": {
            "authenticated": bool(private_status.get("authenticated")),
            "canSubmitOrder": bool(preflight.get("canSubmitOrder")),
            "orderEndpointEnabled": bool(preflight.get("orderEndpointEnabled")),
            "manualConfirmationRequired": bool(preflight.get("manualConfirmationRequired", True)),
            "blockers": blockers,
        },
        "riskBudget": preflight.get("riskBudget") or {},
        "paperSummary": paper.get("summary") or {},
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(f"Wukong professional audit: files={len(files)} blockers={len(blockers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
