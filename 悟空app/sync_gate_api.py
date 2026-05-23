#!/usr/bin/env python3
"""Sync public Gate.io market data for Wukong PWA and app surfaces."""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


GATE_BASE = "https://api.gateio.ws/api/v4"
GATE_PAIRS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT"]
ROOT = Path(__file__).resolve().parent
OUTPUT_PATHS = [
    ROOT / "PWA" / "gate_markets.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/gate_markets.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/gate_markets.json"),
]


def get_json(path: str, query: dict[str, str]) -> Any:
    url = f"{GATE_BASE}{path}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Wukong-Gate-Sync/1.0"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def first(value: Any) -> dict[str, Any]:
    if isinstance(value, list) and value:
        return value[0]
    if isinstance(value, dict):
        return value
    return {}


def build_snapshot() -> dict[str, Any]:
    markets: list[dict[str, Any]] = []
    for symbol in GATE_PAIRS:
        spot = first(get_json("/spot/tickers", {"currency_pair": symbol}))
        futures = first(get_json("/futures/usdt/tickers", {"contract": symbol}))
        markets.append({"symbol": symbol, "spot": spot, "futures": futures})
    return {
        "app": "悟空",
        "source": "Gate.io API v4 public market data",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "markets": markets,
    }


def write_snapshot(snapshot: dict[str, Any]) -> None:
    encoded = json.dumps(snapshot, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")


def main() -> int:
    snapshot = build_snapshot()
    write_snapshot(snapshot)
    print(f"Synced Gate API markets: {len(snapshot['markets'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
