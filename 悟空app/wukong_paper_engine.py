#!/usr/bin/env python3
"""Run Wukong automatic paper trading without submitting real orders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "paper_trading_state.json"
PREFLIGHT_PATH = ROOT / "PWA" / "gate_trade_preflight.json"
SNAPSHOT_PATHS = [
    ROOT / "PWA" / "wukong_latest_snapshot.json",
    ROOT / "wukong_latest_snapshot.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/wukong_latest_snapshot.json"),
]
OUTPUT_PATHS = [
    ROOT / "PWA" / "paper_trading_state.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/paper_trading_state.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/paper_trading_state.json"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_dashboard() -> dict[str, Any]:
    for path in SNAPSHOT_PATHS:
        payload = load_json(path, {})
        if isinstance(payload, dict) and isinstance(payload.get("dashboard"), dict):
            return payload["dashboard"]
        if isinstance(payload, dict) and payload:
            return payload
    return {}


def find_token(dashboard: dict[str, Any], ticker: str) -> dict[str, Any] | None:
    ticker = ticker.upper().replace("_USDT", "")
    for section in ("entryWindow", "opportunities", "contractLaunch", "earlyEntryRadar", "oiAnomalyWatch"):
        for item in dashboard.get(section) or []:
            if str(item.get("ticker") or "").upper() == ticker:
                return item
    return None


def market_price(item: dict[str, Any] | None) -> float | None:
    if not item:
        return None
    market = item.get("market") or {}
    for value in (
        market.get("markPrice"),
        market.get("lastPrice"),
        market.get("price"),
        item.get("markPrice"),
        item.get("price"),
    ):
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        if number > 0:
            return number
    return None


def pnl_pct(entry_price: float, last_price: float, side: str) -> float:
    if entry_price <= 0:
        return 0.0
    raw = (last_price - entry_price) / entry_price * 100
    return -raw if side.startswith("short") else raw


def run_engine() -> dict[str, Any]:
    preflight = load_json(PREFLIGHT_PATH, {})
    previous = load_json(STATE_PATH, {})
    dashboard = load_dashboard()
    paper = preflight.get("paperTrade") or {}
    plan = paper.get("plan") or None
    positions = previous.get("positions") if isinstance(previous.get("positions"), list) else []
    history = previous.get("history") if isinstance(previous.get("history"), list) else []
    generated_at = now_iso()

    if not plan:
        closed = []
        for position in positions:
            position = {**position}
            position["state"] = "closed"
            position["closedAt"] = generated_at
            position["closeReason"] = "signal_disappeared"
            closed.append(position)
        history = (closed + history)[:80]
        positions = []
        state = "flat"
        reason = "入仓信号消失，纸交易已自动清仓"
    else:
        market = str(plan.get("market") or "UNKNOWN_USDT").upper()
        side = str(plan.get("side") or "long-watch")
        ticker = market.replace("_USDT", "")
        token = find_token(dashboard, ticker)
        price = market_price(token) or 1.0
        current = next((item for item in positions if item.get("market") == market and item.get("state") == "open"), None)
        if current:
            current["lastPrice"] = price
            current["updatedAt"] = generated_at
            current["unrealizedPct"] = round(pnl_pct(float(current.get("entryPrice") or price), price, side), 4)
            current["unrealizedUsdt"] = round(float(current.get("maxNotionalUsdt") or 0) * current["unrealizedPct"] / 100, 4)
        else:
            positions = [
                {
                    "market": market,
                    "side": side,
                    "state": "open",
                    "openedAt": generated_at,
                    "updatedAt": generated_at,
                    "entryPrice": price,
                    "lastPrice": price,
                    "leverage": plan.get("leverage"),
                    "maxMarginUsdt": plan.get("maxMarginUsdt"),
                    "maxNotionalUsdt": plan.get("maxNotionalUsdt"),
                    "riskPerTradeUsdt": plan.get("riskPerTradeUsdt"),
                    "stopLossPct": plan.get("stopLossPct"),
                    "maxStopLossPct": plan.get("maxStopLossPct"),
                    "takeProfitTiers": plan.get("takeProfitTiers") or [],
                    "unrealizedPct": 0.0,
                    "unrealizedUsdt": 0.0,
                    "submitRealOrder": False,
                }
            ]
        state = "running"
        reason = "入仓信号存在，纸交易引擎自动运行；真实订单提交关闭"

    total_unrealized = round(sum(float(item.get("unrealizedUsdt") or 0) for item in positions), 4)
    payload = {
        "app": "悟空",
        "mode": "auto-paper-trading",
        "generatedAt": generated_at,
        "state": state,
        "reason": reason,
        "realTradingEnabled": False,
        "canSubmitOrder": False,
        "orderEndpointEnabled": False,
        "positions": positions,
        "history": history[:80],
        "summary": {
            "openPositions": len(positions),
            "closedTrades": len(history),
            "totalUnrealizedUsdt": total_unrealized,
        },
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    return payload


def main() -> int:
    payload = run_engine()
    print(f"Wukong paper engine: {payload['state']} · open={payload['summary']['openPositions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
