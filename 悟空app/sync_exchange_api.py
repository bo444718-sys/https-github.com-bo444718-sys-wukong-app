#!/usr/bin/env python3
"""Sync public Binance, OKX, and Gate market data for Wukong surfaces."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SYMBOLS = [
    {"base": "BTC", "binance": "BTCUSDT", "okx_spot": "BTC-USDT", "okx_swap": "BTC-USDT-SWAP", "gate": "BTC_USDT"},
    {"base": "ETH", "binance": "ETHUSDT", "okx_spot": "ETH-USDT", "okx_swap": "ETH-USDT-SWAP", "gate": "ETH_USDT"},
    {"base": "SOL", "binance": "SOLUSDT", "okx_spot": "SOL-USDT", "okx_swap": "SOL-USDT-SWAP", "gate": "SOL_USDT"},
    {"base": "BNB", "binance": "BNBUSDT", "okx_spot": "BNB-USDT", "okx_swap": "BNB-USDT-SWAP", "gate": "BNB_USDT"},
]

OUTPUT_PATHS = [
    ROOT / "exchange_markets.json",
    ROOT / "PWA" / "exchange_markets.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/exchange_markets.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/exchange_markets.json"),
]
GATE_OUTPUT_PATHS = [
    ROOT / "PWA" / "gate_markets.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/gate_markets.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/gate_markets.json"),
]


def get_json(url: str) -> Any:
    request = urllib.request.Request(url, headers={"User-Agent": "Wukong-Exchange-Sync/1.0"})
    with urllib.request.urlopen(request, timeout=18) as response:
        return json.loads(response.read().decode("utf-8"))


def first(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        data = value.get("data")
        if isinstance(data, list) and data:
            return data[0]
        return value
    return {}


def safe_fetch(url: str) -> tuple[dict[str, Any], str]:
    try:
        return first(get_json(url)), ""
    except Exception as exc:
        return {}, str(exc)


def url(base: str, query: dict[str, str]) -> str:
    return f"{base}?{urllib.parse.urlencode(query)}"


def build_market(row: dict[str, str]) -> dict[str, Any]:
    symbol = row["base"]
    binance_spot, binance_spot_error = safe_fetch(url("https://api.binance.com/api/v3/ticker/24hr", {"symbol": row["binance"]}))
    binance_futures, binance_futures_error = safe_fetch(url("https://fapi.binance.com/fapi/v1/ticker/24hr", {"symbol": row["binance"]}))
    binance_funding, binance_funding_error = safe_fetch(url("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": row["binance"]}))

    okx_spot, okx_spot_error = safe_fetch(url("https://www.okx.com/api/v5/market/ticker", {"instId": row["okx_spot"]}))
    okx_swap, okx_swap_error = safe_fetch(url("https://www.okx.com/api/v5/market/ticker", {"instId": row["okx_swap"]}))
    okx_funding, okx_funding_error = safe_fetch(url("https://www.okx.com/api/v5/public/funding-rate", {"instId": row["okx_swap"]}))

    gate_spot, gate_spot_error = safe_fetch(url("https://api.gateio.ws/api/v4/spot/tickers", {"currency_pair": row["gate"]}))
    gate_futures, gate_futures_error = safe_fetch(url("https://api.gateio.ws/api/v4/futures/usdt/tickers", {"contract": row["gate"]}))

    return {
        "symbol": symbol,
        "pair": f"{symbol}/USDT",
        "venues": {
            "binance": {
                "spot": binance_spot,
                "futures": binance_futures,
                "funding": binance_funding,
                "errors": [item for item in [binance_spot_error, binance_futures_error, binance_funding_error] if item],
            },
            "okx": {
                "spot": okx_spot,
                "futures": okx_swap,
                "funding": okx_funding,
                "errors": [item for item in [okx_spot_error, okx_swap_error, okx_funding_error] if item],
            },
            "gate": {
                "spot": gate_spot,
                "futures": gate_futures,
                "funding": gate_futures,
                "errors": [item for item in [gate_spot_error, gate_futures_error] if item],
            },
        },
    }


def venue_online(markets: list[dict[str, Any]], venue: str) -> bool:
    for market in markets:
        data = market.get("venues", {}).get(venue, {})
        if data.get("spot") or data.get("futures"):
            return True
    return False


def gate_snapshot(markets: list[dict[str, Any]], generated_at: str) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for market in markets:
        gate = market.get("venues", {}).get("gate", {})
        rows.append({
            "symbol": f"{market.get('symbol', '')}_USDT",
            "spot": gate.get("spot") or {},
            "futures": gate.get("futures") or {},
        })
    return {
        "app": "悟空",
        "source": "Gate.io API v4 public market data",
        "generatedAt": generated_at,
        "markets": rows,
    }


def build_snapshot() -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).isoformat()
    markets = [build_market(row) for row in SYMBOLS]
    venues = {
        "binance": {"name": "Binance", "online": venue_online(markets, "binance"), "mode": "public-readonly"},
        "okx": {"name": "OKX", "online": venue_online(markets, "okx"), "mode": "public-readonly"},
        "gate": {"name": "Gate", "online": venue_online(markets, "gate"), "mode": "public-readonly"},
    }
    return {
        "app": "悟空",
        "source": "Binance + OKX + Gate public market APIs",
        "generatedAt": generated_at,
        "refreshSeconds": 60,
        "privateTrading": "disabled",
        "venues": venues,
        "markets": markets,
    }


def write_json(paths: list[Path], payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8")
        except PermissionError:
            print(f"Skip protected path: {path}")


def main() -> int:
    snapshot = build_snapshot()
    write_json(OUTPUT_PATHS, snapshot)
    write_json(GATE_OUTPUT_PATHS, gate_snapshot(snapshot["markets"], snapshot["generatedAt"]))
    online = [key for key, value in snapshot["venues"].items() if value["online"]]
    print(f"Synced exchange APIs: {', '.join(online) or 'no venues'} · {len(snapshot['markets'])} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
