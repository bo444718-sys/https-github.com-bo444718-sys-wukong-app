#!/usr/bin/env python3
"""Create a dry-run Gate trade preflight plan without submitting orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from gate_private_status import build_status
from gate_private_status import EXIT_RULE
from gate_private_status import PROTECTION_LAYERS


ROOT = Path(__file__).resolve().parent
SNAPSHOT_PATHS = [
    ROOT / "PWA" / "wukong_latest_snapshot.json",
    ROOT / "wukong_latest_snapshot.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/wukong_latest_snapshot.json"),
]
OUTPUT_PATHS = [
    ROOT / "PWA" / "gate_trade_preflight.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/gate_trade_preflight.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/gate_trade_preflight.json"),
]


def load_dashboard() -> dict[str, Any]:
    for path in SNAPSHOT_PATHS:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        dashboard = payload.get("dashboard") if isinstance(payload, dict) else None
        if isinstance(dashboard, dict):
            return dashboard
        if isinstance(payload, dict):
            return payload
    return {}


def token_score(item: dict[str, Any]) -> float:
    signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
    for key in ("score", "primaryOpportunityScore", "heatScore"):
        try:
            value = float(signal.get(key) if key == "score" else item.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0.0


def unique_signal_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section in ("entryWindow", "opportunities", "contractLaunch", "earlyEntryRadar"):
        for item in dashboard.get(section) or []:
            if not isinstance(item, dict):
                continue
            ticker = str(item.get("ticker") or "").upper()
            if not ticker:
                continue
            rows.append({**item, "_signalSection": section})
    by_ticker: dict[str, dict[str, Any]] = {}
    for item in rows:
        ticker = str(item.get("ticker") or "").upper()
        previous = by_ticker.get(ticker)
        if not previous or token_score(item) > token_score(previous):
            by_ticker[ticker] = item
    return sorted(by_ticker.values(), key=token_score, reverse=True)


def build_signal_gate(dashboard: dict[str, Any], blockers: list[str]) -> dict[str, Any]:
    tokens = unique_signal_tokens(dashboard)
    primary = tokens[0] if tokens else None
    signal_active = bool(primary)
    blocked = bool(blockers)
    if not signal_active:
        state = "auto-closed"
        reason = "入仓信号已消失，交易闸门自动关闭"
    elif blocked:
        state = "armed-blocked"
        reason = "入仓信号存在，但实盘订单提交被风控阻断"
    else:
        state = "armed-manual-confirm"
        reason = "入仓信号存在，仅生成待确认计划，不自动提交实盘"
    return {
        "signalActive": signal_active,
        "state": state,
        "reason": reason,
        "autoOpenWhenSignalAppears": False,
        "autoCloseWhenSignalDisappears": True,
        "realOrderSyncEnabled": False,
        "manualConfirmationRequired": True,
        "primary": {
            "ticker": primary.get("ticker"),
            "section": primary.get("_signalSection"),
            "stage": primary.get("currentStage") or primary.get("stage"),
            "score": token_score(primary),
        } if primary else None,
        "queue": [
            {
                "ticker": item.get("ticker"),
                "section": item.get("_signalSection"),
                "stage": item.get("currentStage") or item.get("stage"),
                "score": token_score(item),
            }
            for item in tokens[:8]
        ],
    }


def build_paper_trade_plan(signal_gate: dict[str, Any], risk_budget: dict[str, Any]) -> dict[str, Any]:
    primary = signal_gate.get("primary") or {}
    signal_active = bool(signal_gate.get("signalActive"))
    max_notional = risk_budget.get("maxNotionalUsdt")
    max_margin = risk_budget.get("maxMarginUsdt")
    leverage = risk_budget.get("leverage")
    risk_per_trade = risk_budget.get("riskPerTradeUsdt")
    if not signal_active:
        return {
            "enabled": True,
            "state": "closed",
            "reason": "入仓信号消失，纸交易计划自动关闭",
            "autoOpenWhenSignalAppears": True,
            "autoCloseWhenSignalDisappears": True,
            "plan": None,
        }
    ticker = str(primary.get("ticker") or "UNKNOWN").upper()
    return {
        "enabled": True,
        "state": "auto-paper-open",
        "reason": "入仓信号出现，已自动生成纸交易计划；不会提交真实订单",
        "autoOpenWhenSignalAppears": True,
        "autoCloseWhenSignalDisappears": True,
        "plan": {
            "market": f"{ticker}_USDT",
            "side": "long-watch",
            "leverage": leverage,
            "maxMarginUsdt": max_margin,
            "maxNotionalUsdt": max_notional,
            "riskPerTradeUsdt": risk_per_trade,
            "stopLossPct": EXIT_RULE["baseStopLossPct"],
            "maxStopLossPct": EXIT_RULE["maxStopLossPct"],
            "takeProfitTiers": EXIT_RULE["takeProfitTiers"],
            "sourceSignal": primary,
            "submitRealOrder": False,
        },
    }


def build_preflight() -> dict[str, Any]:
    status = build_status()
    blockers = []
    if not status.get("authenticated"):
        blockers.append("Gate 私有 API 未验证")
    if status.get("liveTradingRequested"):
        blockers.append(status.get("liveTradingBlockedReason") or "实盘安全锁未解锁")
    if status.get("keyRotationRequired"):
        blockers.append("当前 Gate Key 已暴露，必须换新 Key")
    if not next((item.get("ok") for item in status.get("manualLiveReadiness", []) if item.get("name") == "IP 白名单"), False):
        blockers.append("未配置 Gate IP 白名单")
    blockers.extend([
        *([] if next((item.get("ok") for item in status.get("manualLiveReadiness", []) if item.get("name") == "单笔限额"), False) else ["未配置单笔最大名义价值"]),
        *([] if next((item.get("ok") for item in status.get("manualLiveReadiness", []) if item.get("name") == "每日熔断"), False) else ["未配置每日最大亏损"]),
        *([] if next((item.get("ok") for item in status.get("manualLiveReadiness", []) if item.get("name") == "手动确认"), False) else ["未配置手动确认签名"]),
    ])
    dashboard = load_dashboard()
    signal_gate = build_signal_gate(dashboard, blockers)
    risk_budget = status.get("riskBudget", {})
    paper_trade = build_paper_trade_plan(signal_gate, risk_budget)
    return {
        "app": "悟空",
        "exchange": "gate",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "dry-run",
        "canSubmitOrder": False,
        "manualConfirmationRequired": True,
        "keySafetyState": status.get("keySafetyState"),
        "keyRotationRequired": status.get("keyRotationRequired"),
        "manualLiveReadiness": status.get("manualLiveReadiness", []),
        "riskBudget": risk_budget,
        "orderEndpointEnabled": False,
        "signalTradeGate": signal_gate,
        "paperTrade": paper_trade,
        "telegramConfirm": {
            "command": "/confirm_live",
            "enabled": False,
            "state": "preflight-only",
            "reason": "Telegram 一键确认只返回实盘预检结果，不会自动提交 Gate 订单",
            "requires": ["新 Key", "IP 白名单", "单笔限额", "每日熔断", "手动确认"],
        },
        "exitRule": EXIT_RULE,
        "protectionPolicy": {
            "name": "开仓附带 → 开仓后补挂 → 软件层兜底",
            "layers": PROTECTION_LAYERS,
            "executionOrder": ["entryAttach", "postEntryNative", "softwareFallback"],
            "neverNakedPosition": True,
        },
        "blockers": blockers,
        "samplePlan": {
            "market": "BTC_USDT",
            "side": "buy",
            "orderType": "limit",
            "timeInForce": "gtc",
            "maxNotionalUsdt": (status.get("riskBudget") or {}).get("maxNotionalUsdt"),
            "maxMarginUsdt": (status.get("riskBudget") or {}).get("maxMarginUsdt"),
            "riskPerTradeUsdt": (status.get("riskBudget") or {}).get("riskPerTradeUsdt"),
            "takeProfit": [
                "第一档 +3.5% 平 25%",
                "第二档 +7.5% 平 25%",
                "第三档 +12% 平 50%",
            ],
            "stopLoss": "基础止损 2.4%，最多放宽到 5.5%",
            "protectionFlow": [
                "第一层：开仓请求直接附带原生止盈止损",
                "第二层：若附带参数被拒，开仓后补挂原生 OCO / 条件保护单",
                "第三层：若原生保护失败，软件层执行分批止盈、固定止损、追踪止盈、超时离场",
            ],
            "signalLinkedExecution": signal_gate.get("reason"),
            "paperTrade": paper_trade.get("reason"),
            "risk": "只生成计划，不发送到 Gate",
        },
    }


def main() -> int:
    payload = build_preflight()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(f"Gate trade preflight: dry-run · blockers={len(payload['blockers'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
