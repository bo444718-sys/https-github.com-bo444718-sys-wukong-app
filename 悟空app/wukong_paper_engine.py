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
MAX_POSITION_AGE_SECONDS = 6 * 60 * 60
REENTRY_COOLDOWN_SECONDS = 30 * 60
TRAILING_ACTIVATION_PCT = 7.5
TRAILING_GIVEBACK_PCT = 3.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


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


def close_position(position: dict[str, Any], reason: str, price: float, generated_at: str) -> dict[str, Any]:
    closed = {**position}
    closed["state"] = "closed"
    closed["closedAt"] = generated_at
    closed["closeReason"] = reason
    closed["closePrice"] = price
    closed["remainingPct"] = closed.get("remainingPct", 100)
    closed["submitRealOrder"] = False
    return closed


def update_open_position(position: dict[str, Any], price: float, side: str, generated_at: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    position = {**position}
    entry = float(position.get("entryPrice") or price)
    pnl = round(pnl_pct(entry, price, side), 4)
    notional = float(position.get("maxNotionalUsdt") or 0)
    remaining_pct = float(position.get("remainingPct") if position.get("remainingPct") is not None else 100)
    filled_tiers = list(position.get("filledTakeProfits") or [])
    position["lastPrice"] = price
    position["updatedAt"] = generated_at
    position["unrealizedPct"] = pnl
    position["remainingPct"] = round(remaining_pct, 4)
    position["unrealizedUsdt"] = round(notional * (remaining_pct / 100) * pnl / 100, 4)
    position["maxPnlPct"] = max(float(position.get("maxPnlPct") or pnl), pnl)

    stop_loss = float(position.get("stopLossPct") or 0)
    if stop_loss and pnl <= -abs(stop_loss):
        return None, close_position(position, "stop_loss", price, generated_at)

    for index, tier in enumerate(position.get("takeProfitTiers") or []):
        if index in filled_tiers:
            continue
        trigger = float(tier.get("triggerPct") or 0)
        close_pct = float(tier.get("closePct") or 0)
        if trigger and close_pct and pnl >= trigger:
            filled_tiers.append(index)
            close_size = min(remaining_pct, close_pct)
            realized = notional * (close_size / 100) * pnl / 100
            position["realizedUsdt"] = round(float(position.get("realizedUsdt") or 0) + realized, 4)
            remaining_pct = max(0.0, remaining_pct - close_size)
            position["remainingPct"] = round(remaining_pct, 4)
            position["filledTakeProfits"] = filled_tiers
            position["lastTakeProfitAt"] = generated_at
    if remaining_pct <= 0:
        return None, close_position(position, "take_profit_complete", price, generated_at)

    high_water = float(position.get("maxPnlPct") or pnl)
    if high_water >= TRAILING_ACTIVATION_PCT and pnl <= high_water - TRAILING_GIVEBACK_PCT:
        return None, close_position(position, "trailing_take_profit", price, generated_at)

    opened = parse_time(position.get("openedAt"))
    if opened:
        age = (datetime.fromisoformat(generated_at).astimezone(timezone.utc) - opened.astimezone(timezone.utc)).total_seconds()
        if age >= MAX_POSITION_AGE_SECONDS:
            return None, close_position(position, "time_exit", price, generated_at)
    return position, None


def in_reentry_cooldown(history: list[dict[str, Any]], market: str, generated_at: str) -> tuple[bool, str]:
    now = datetime.fromisoformat(generated_at).astimezone(timezone.utc)
    for item in history:
        if item.get("market") != market:
            continue
        closed_at = parse_time(item.get("closedAt"))
        if not closed_at:
            continue
        age = (now - closed_at.astimezone(timezone.utc)).total_seconds()
        if age < REENTRY_COOLDOWN_SECONDS and item.get("closeReason") in {"stop_loss", "take_profit_complete", "trailing_take_profit", "time_exit"}:
            left = int((REENTRY_COOLDOWN_SECONDS - age) // 60) + 1
            return True, f"{market} 刚按 {item.get('closeReason')} 离场，冷却还剩约 {left} 分钟"
    return False, ""


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
            price = float(position.get("lastPrice") or position.get("entryPrice") or 0)
            closed.append(close_position(position, "signal_disappeared", price, generated_at))
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
        rotated = []
        kept_positions = []
        for position in positions:
            if position.get("market") == market and position.get("state") == "open":
                kept_positions.append(position)
            else:
                old_price = float(position.get("lastPrice") or position.get("entryPrice") or 0)
                rotated.append(close_position(position, "signal_rotated", old_price, generated_at))
        if rotated:
            history = (rotated + history)[:80]
        positions = kept_positions
        current = next((item for item in positions if item.get("market") == market and item.get("state") == "open"), None)
        if current:
            updated, closed = update_open_position(current, price, side, generated_at)
            if closed:
                history = ([closed] + history)[:80]
                positions = []
            elif updated:
                positions = [updated]
        else:
            cooling, cooldown_reason = in_reentry_cooldown(history, market, generated_at)
            if cooling:
                positions = []
                history = ([{"market": market, "state": "skipped", "closedAt": generated_at, "closeReason": "cooldown", "detail": cooldown_reason}] + history)[:80]
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
                        "remainingPct": 100.0,
                        "filledTakeProfits": [],
                        "realizedUsdt": 0.0,
                        "maxPnlPct": 0.0,
                        "trailingActivationPct": TRAILING_ACTIVATION_PCT,
                        "trailingGivebackPct": TRAILING_GIVEBACK_PCT,
                        "maxAgeSeconds": MAX_POSITION_AGE_SECONDS,
                        "reentryCooldownSeconds": REENTRY_COOLDOWN_SECONDS,
                        "unrealizedPct": 0.0,
                        "unrealizedUsdt": 0.0,
                        "submitRealOrder": False,
                    }
                ]
        state = "running" if positions else "flat"
        reason = "入仓信号存在，纸交易引擎自动运行；真实订单提交关闭" if positions else "纸交易已按止盈止损/追踪/超时规则离场"

    total_unrealized = round(sum(float(item.get("unrealizedUsdt") or 0) for item in positions), 4)
    total_realized = round(sum(float(item.get("realizedUsdt") or 0) for item in history), 4)
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
            "totalRealizedUsdt": total_realized,
            "maxPositionAgeSeconds": MAX_POSITION_AGE_SECONDS,
            "trailingActivationPct": TRAILING_ACTIVATION_PCT,
            "trailingGivebackPct": TRAILING_GIVEBACK_PCT,
            "reentryCooldownSeconds": REENTRY_COOLDOWN_SECONDS,
        },
    }
    STATE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8")
        except PermissionError:
            print(f"Skip protected path: {path}")
    return payload


def main() -> int:
    payload = run_engine()
    print(f"Wukong paper engine: {payload['state']} · open={payload['summary']['openPositions']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
