#!/usr/bin/env python3
"""Scan Binance USDT futures for 4H EMA21 crossing above EMA55."""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUTPUT_PATHS = [
    ROOT / "ema_cross_4h.json",
    ROOT / "PWA" / "ema_cross_4h.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/ema_cross_4h.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/ema_cross_4h.json"),
]
BOOTSTRAP_PATHS = [
    ROOT / "PWA" / "ema_cross_4h_bootstrap.js",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/ema_cross_4h_bootstrap.js"),
]
BASE = "https://fapi.binance.com"
INTERVAL = "4h"
KLINE_LIMIT = 90
MAX_WORKERS = 10


def get_json(path: str, query: dict[str, Any] | None = None, timeout: int = 18) -> Any:
    url = f"{BASE}{path}"
    if query:
        url = f"{url}?{urllib.parse.urlencode(query)}"
    request = urllib.request.Request(url, headers={"User-Agent": "Wukong-EMA-Cross/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ema(values: list[float], period: int) -> list[float]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    rows = [values[0]]
    for value in values[1:]:
        rows.append(value * alpha + rows[-1] * (1 - alpha))
    return rows


def usdt_symbols() -> list[str]:
    payload = get_json("/fapi/v1/exchangeInfo", timeout=25)
    rows = []
    for item in payload.get("symbols", []):
        if item.get("quoteAsset") != "USDT":
            continue
        if item.get("contractType") != "PERPETUAL":
            continue
        if item.get("status") != "TRADING":
            continue
        symbol = item.get("symbol")
        if symbol:
            rows.append(symbol)
    return sorted(rows)


def scan_symbol(symbol: str) -> dict[str, Any] | None:
    klines = get_json("/fapi/v1/klines", {"symbol": symbol, "interval": INTERVAL, "limit": KLINE_LIMIT}, timeout=18)
    closes = [float(row[4]) for row in klines if len(row) > 4]
    if len(closes) < 60:
        return None
    ema21 = ema(closes, 21)
    ema55 = ema(closes, 55)
    crossed = ema21[-2] <= ema55[-2] and ema21[-1] > ema55[-1]
    if not crossed:
        return None
    last = klines[-1]
    previous_close = closes[-2]
    last_close = closes[-1]
    change = (last_close - previous_close) / previous_close * 100 if previous_close else 0
    spread = (ema21[-1] - ema55[-1]) / ema55[-1] * 100 if ema55[-1] else 0
    return {
        "ticker": symbol.replace("USDT", ""),
        "symbol": symbol,
        "pair": f"{symbol.replace('USDT', '')}/USDT",
        "interval": INTERVAL,
        "close": last_close,
        "changeLastCandlePct": round(change, 4),
        "ema21": round(ema21[-1], 10),
        "ema55": round(ema55[-1], 10),
        "emaSpreadPct": round(spread, 4),
        "candleCloseTime": datetime.fromtimestamp(last[6] / 1000, timezone.utc).isoformat() if len(last) > 6 else "",
        "signal": "4H EMA21 上穿 EMA55",
    }


def build_snapshot() -> dict[str, Any]:
    started = time.time()
    max_symbols = int(os.getenv("WUKONG_EMA_MAX_SYMBOLS", "0") or "0")
    symbols = usdt_symbols()
    if max_symbols > 0:
        symbols = symbols[:max_symbols]
    rows: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(scan_symbol, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                row = future.result()
                if row:
                    rows.append(row)
            except Exception as exc:
                errors.append({"symbol": symbol, "error": str(exc)[:160]})
    rows.sort(key=lambda item: item.get("emaSpreadPct", 0), reverse=True)
    return {
        "app": "悟空",
        "source": "Binance USDT perpetual klines",
        "mode": "public-readonly",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "interval": INTERVAL,
        "rule": "EMA21 上穿 EMA55",
        "symbolsScanned": len(symbols),
        "matches": len(rows),
        "durationSeconds": round(time.time() - started, 2),
        "items": rows,
        "errors": errors[:20],
    }


def write_json(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8")
        except PermissionError:
            print(f"Skip protected path: {path}")
    bootstrap = "window.WUKONG_EMA_CROSS_4H = " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + ";\n"
    for path in BOOTSTRAP_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(bootstrap, encoding="utf-8")
        except PermissionError:
            print(f"Skip protected path: {path}")


def main() -> int:
    payload = build_snapshot()
    write_json(payload)
    print(f"EMA 4H cross: {payload['matches']} / {payload['symbolsScanned']} symbols")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
