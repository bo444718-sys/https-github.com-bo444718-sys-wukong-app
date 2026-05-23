#!/usr/bin/env python3
"""Check Gate private API binding status without placing orders."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
ENV_PATHS = [
    ROOT / ".env.gate",
    Path("/Users/wangbo/.hermes/wukong_telegram/.env.gate"),
    Path("/Users/wangbo/.hermes/.env"),
]
OUTPUT_PATHS = [
    ROOT / "PWA" / "gate_private_status.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/gate_private_status.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/gate_private_status.json"),
]
GATE_BASE = "https://api.gateio.ws"
EXPOSED_KEY_HASHES = {
    "b5c8d44c0e6c71188ee15917a4efe5f8224f13c5f45995f70039c57ec21a9991",
    "1d6715bc905e34455a183ef86a44c3db5f7754e62a7b9708c33862ac2b23eebe",
    "2e566cf9dcc99fffcec6af62b532ad5c",
    "68c4e9299d2153b8b36b3fd8087024c7134f72b9602a08f5dfb3c606fdf4d174",
}
EXPOSED_SECRET_HASHES = {
    "9d8970f5777ac09e9d7c5546487a9f910a9754daec112ec7e8dd221b9b5a701b",
    "149c46e8ec1404a424f289308ab50628cd5f48d1aade51b7efc2ce6d838ff396",
    "2e566cf9dcc99fffcec6af62b532ad5c",
    "68c4e9299d2153b8b36b3fd8087024c7134f72b9602a08f5dfb3c606fdf4d174",
}
EXIT_RULE = {
    "takeProfitTiers": [
        {"triggerPct": 3.5, "closePct": 25},
        {"triggerPct": 7.5, "closePct": 25},
        {"triggerPct": 12.0, "closePct": 50},
    ],
    "baseStopLossPct": 2.4,
    "maxStopLossPct": 5.5,
}
PROTECTION_LAYERS = [
    {
        "id": "entryAttach",
        "name": "开仓附带",
        "state": "planned",
        "detail": "下单时优先随开仓请求附带原生止盈止损，让仓位成交即带保护",
        "appliesTo": ["spot", "futures"],
    },
    {
        "id": "postEntryNative",
        "name": "开仓后补挂",
        "state": "planned",
        "detail": "如果交易所拒绝附带保护参数，先保留开仓，再补挂原生 OCO / 条件保护单",
        "appliesTo": ["spot", "futures"],
    },
    {
        "id": "softwareFallback",
        "name": "软件层兜底",
        "state": "armed",
        "detail": "原生保护单失败时，由主循环执行分批止盈、固定止损、追踪止盈和超时离场",
        "appliesTo": ["spot", "futures"],
    },
]


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values.setdefault(key.strip(), value.strip().strip('"').strip("'"))
    for key in [
        "GATE_API_KEY",
        "GATE_API_SECRET",
        "WUKONG_GATE_TRADING_MODE",
        "WUKONG_GATE_LIVE_UNLOCK",
        "WUKONG_GATE_ACCOUNT_EQUITY_USDT",
        "WUKONG_GATE_LEVERAGE",
        "WUKONG_GATE_MAX_NOTIONAL_USDT",
        "WUKONG_GATE_MAX_MARGIN_USDT",
        "WUKONG_GATE_RISK_PER_TRADE_USDT",
        "WUKONG_GATE_DAILY_MAX_LOSS_USDT",
        "WUKONG_GATE_CONSECUTIVE_LOSS_LIMIT",
        "WUKONG_GATE_CONFIRMATION_MODE",
    ]:
        if os.getenv(key):
            values[key] = os.getenv(key, "")
    return values


def masked(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 8:
        return "****"
    return f"{value[:4]}...{value[-4:]}"


def key_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest() if value else ""


def env_float(env: dict[str, str], key: str) -> float | None:
    try:
        value = float(env.get(key, ""))
    except ValueError:
        return None
    return value if value > 0 else None


def env_int(env: dict[str, str], key: str) -> int | None:
    try:
        value = int(float(env.get(key, "")))
    except ValueError:
        return None
    return value if value > 0 else None


def sign(method: str, path: str, query: str, body: bytes, secret: str, timestamp: str) -> str:
    body_hash = hashlib.sha512(body).hexdigest()
    payload = "\n".join([method.upper(), path, query, body_hash, timestamp])
    return hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha512).hexdigest()


def gate_request(method: str, path: str, *, query: dict[str, str] | None = None, body: dict[str, Any] | None = None) -> Any:
    env = load_env()
    api_key = env.get("GATE_API_KEY", "")
    secret = env.get("GATE_API_SECRET", "")
    if not api_key or not secret:
        raise RuntimeError("Gate API key is not configured")
    query_string = urllib.parse.urlencode(query or {})
    raw_body = json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8") if body else b""
    timestamp = str(int(time.time()))
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "KEY": api_key,
        "Timestamp": timestamp,
        "SIGN": sign(method, path, query_string, raw_body, secret, timestamp),
        "User-Agent": "Wukong-Gate-Private-Status/1.0",
    }
    url = f"{GATE_BASE}{path}"
    if query_string:
        url = f"{url}?{query_string}"
    request = urllib.request.Request(url, data=raw_body if method.upper() != "GET" else None, headers=headers, method=method.upper())
    with urllib.request.urlopen(request, timeout=18) as response:
        raw = response.read().decode("utf-8")
        return json.loads(raw) if raw else {}


def build_status() -> dict[str, Any]:
    env = load_env()
    api_key = env.get("GATE_API_KEY", "")
    secret = env.get("GATE_API_SECRET", "")
    api_key_hash = key_hash(api_key)
    secret_hash = key_hash(secret)
    key_is_exposed = api_key_hash in EXPOSED_KEY_HASHES
    secret_is_exposed = secret_hash in EXPOSED_SECRET_HASHES
    credential_is_exposed = key_is_exposed or secret_is_exposed
    trading_mode = env.get("WUKONG_GATE_TRADING_MODE", "paper").lower()
    account_equity = env_float(env, "WUKONG_GATE_ACCOUNT_EQUITY_USDT")
    leverage = env_float(env, "WUKONG_GATE_LEVERAGE")
    max_notional = env_float(env, "WUKONG_GATE_MAX_NOTIONAL_USDT")
    max_margin = env_float(env, "WUKONG_GATE_MAX_MARGIN_USDT")
    risk_per_trade = env_float(env, "WUKONG_GATE_RISK_PER_TRADE_USDT")
    daily_max_loss = env_float(env, "WUKONG_GATE_DAILY_MAX_LOSS_USDT")
    consecutive_loss_limit = env_int(env, "WUKONG_GATE_CONSECUTIVE_LOSS_LIMIT")
    confirmation_mode = env.get("WUKONG_GATE_CONFIRMATION_MODE", "").lower()
    limits_ready = bool(max_notional and max_margin and risk_per_trade)
    circuit_ready = bool(daily_max_loss and consecutive_loss_limit)
    confirmation_ready = confirmation_mode == "manual"
    live_requested = trading_mode in {"live", "live_requested", "real"}
    live_unlocked = env.get("WUKONG_GATE_LIVE_UNLOCK", "").strip() == "I_UNDERSTAND_AND_ACCEPT_REAL_LOSS_RISK"
    live_block_reason = ""
    if live_requested:
        live_block_reason = "当前 Key/Secret 已在聊天中暴露，请先撤销旧 Key 并换新 Key；自动实盘下单未解锁" if credential_is_exposed else "实盘必须先通过手动确认、限额、熔断和止损配置"
    manual_live_ready = bool(api_key and secret and not credential_is_exposed)
    status: dict[str, Any] = {
        "app": "悟空",
        "exchange": "gate",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "configured": bool(api_key and env.get("GATE_API_SECRET")),
        "authenticated": False,
        "keyMasked": masked(api_key),
        "keyFingerprint": api_key_hash[:12] if api_key_hash else "",
        "secretFingerprint": secret_hash[:12] if secret_hash else "",
        "keySafetyState": "exposed" if credential_is_exposed else ("candidate" if api_key and secret else "missing"),
        "keyRotationRequired": credential_is_exposed,
        "secretRotationRequired": secret_is_exposed,
        "tradingMode": "paper",
        "requestedTradingMode": "live" if live_requested else "paper",
        "liveTradingEnabled": False,
        "liveTradingRequested": live_requested,
        "liveTradingUnlocked": False,
        "liveTradingBlockedReason": live_block_reason,
        "orderEndpointEnabled": False,
        "manualLiveCandidate": manual_live_ready,
        "manualConfirmationRequired": True,
        "riskBudget": {
            "accountEquityUsdt": account_equity,
            "leverage": leverage,
            "maxNotionalUsdt": max_notional,
            "maxMarginUsdt": max_margin,
            "riskPerTradeUsdt": risk_per_trade,
            "dailyMaxLossUsdt": daily_max_loss,
            "consecutiveLossLimit": consecutive_loss_limit,
            "confirmationMode": confirmation_mode or "unset",
            "baseStopLossPct": EXIT_RULE["baseStopLossPct"],
            "maxStopLossPct": EXIT_RULE["maxStopLossPct"],
        },
        "exitRule": EXIT_RULE,
        "protectionPolicy": {
            "name": "开仓附带 → 开仓后补挂 → 软件层兜底",
            "layers": PROTECTION_LAYERS,
            "neverNakedPosition": True,
            "softwareFallbackEnabled": True,
        },
        "riskControls": [
            {"name": "Key 安全", "state": "blocked" if credential_is_exposed else ("ready" if api_key and secret else "required"), "detail": "当前 Key/Secret 已暴露，实盘必须换新 Key" if credential_is_exposed else "Key/Secret 未命中已暴露清单"},
            {"name": "单笔限额", "state": "ready" if limits_ready else "required", "detail": f"最大名义 {max_notional:g}U / 保证金 {max_margin:g}U / 单笔亏损 {risk_per_trade:g}U" if limits_ready else "未设置最大单笔 USDT 名义价值"},
            {"name": "每日熔断", "state": "ready" if circuit_ready else "required", "detail": f"日亏损 {daily_max_loss:g}U 熔断，连续亏损 {consecutive_loss_limit} 笔停止" if circuit_ready else "未设置每日最大亏损和连续亏损停止"},
            {"name": "止盈止损", "state": "ready", "detail": "+3.5%/25%, +7.5%/25%, +12%/50%; SL 2.4%-5.5%"},
            {"name": "三层保护", "state": "ready", "detail": "开仓附带 → 补挂原生保护 → 软件兜底"},
            {"name": "手动确认", "state": "ready" if confirmation_ready else "locked", "detail": "手动确认模式已配置" if confirmation_ready else "自动开单关闭，只允许生成待确认订单"},
        ],
        "nextActions": [
            "撤销聊天中暴露过的 Gate Key",
            "创建新 Key，并只开放必要交易权限",
            "设置 Gate IP 白名单",
            "配置单笔限额和每日亏损熔断",
            "先跑至少 24 小时纸交易，再进入手动确认实盘",
        ],
        "manualLiveReadiness": [
            {"name": "新 Key", "ok": bool(api_key and secret and not credential_is_exposed), "detail": "必须撤销旧 Key 并换新 Key"},
            {"name": "IP 白名单", "ok": False, "detail": "等待配置固定出口 IP 白名单"},
            {"name": "单笔限额", "ok": limits_ready, "detail": f"最大名义 {max_notional:g}U，最大保证金 {max_margin:g}U，单笔风险 {risk_per_trade:g}U" if limits_ready else "等待配置最大名义价值"},
            {"name": "每日熔断", "ok": circuit_ready, "detail": f"每日亏损 {daily_max_loss:g}U / 连亏 {consecutive_loss_limit} 笔停止" if circuit_ready else "等待配置每日最大亏损"},
            {"name": "手动确认", "ok": confirmation_ready, "detail": "manual 模式已配置" if confirmation_ready else "等待配置确认签名"},
        ],
        "message": "Gate API 未配置" if not api_key else ("已收到实盘申请，但安全锁已拦截" if live_requested else "Gate API 已绑定，实盘开单保持关闭"),
        "balances": [],
        "errors": [],
    }
    if not status["configured"]:
        return status
    try:
        accounts = gate_request("GET", "/api/v4/spot/accounts")
        balances = []
        for item in accounts if isinstance(accounts, list) else []:
            available = float(item.get("available") or 0)
            locked = float(item.get("locked") or 0)
            if available or locked or item.get("currency") == "USDT":
                balances.append({
                    "currency": item.get("currency"),
                    "available": item.get("available"),
                    "locked": item.get("locked"),
                })
        status["authenticated"] = True
        status["message"] = "Gate 私有 API 已验证；实盘申请已被安全锁拦截" if live_requested else "Gate 私有 API 已验证；当前仅允许读取账户和纸交易"
        status["balances"] = balances[:12]
        if live_requested and live_unlocked:
            status["liveTradingBlockedReason"] = "安全策略仍要求完成限额、熔断、止损、手动确认和 IP 白名单后才能进入实盘候选"
    except urllib.error.HTTPError as exc:
        status["errors"].append(f"Gate HTTP {exc.code}")
        status["message"] = "Gate 私有 API 验证失败，请检查 Key 权限或 IP 白名单"
    except Exception as exc:
        status["errors"].append(str(exc))
        status["message"] = "Gate 私有 API 验证失败"
    return status


def write_status(status: dict[str, Any]) -> None:
    encoded = json.dumps(status, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


def main() -> int:
    status = build_status()
    write_status(status)
    state = "authenticated" if status["authenticated"] else "not-authenticated"
    print(f"Gate private status: {state} · live trading disabled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
