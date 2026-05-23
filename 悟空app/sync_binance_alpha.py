#!/usr/bin/env python3
"""Build the Wukong Binance Alpha snapshot from the live Wukong dashboard."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
SNAPSHOT_CANDIDATES = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/wukong_latest_snapshot.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/wukong_latest_snapshot.json"),
    ROOT / "PWA" / "wukong_latest_snapshot.json",
    ROOT / "wukong_latest_snapshot.json",
]
OUTPUT_PATHS = [
    ROOT / "PWA" / "binance_alpha.json",
    ROOT / "binance_alpha.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/binance_alpha.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/binance_alpha.json"),
]


def load_dashboard() -> dict[str, Any]:
    for path in SNAPSHOT_CANDIDATES:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        dashboard = payload.get("dashboard") or payload
        if isinstance(dashboard, dict):
            return dashboard
    return {}


def number(value: Any, default: float = 0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def token_metric(item: dict[str, Any]) -> dict[str, Any]:
    market = item.get("market") or {}
    signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
    source = item.get("sourceBreakdown") or {}
    dex_identity = item.get("dexIdentity") or {}
    oi = market.get("oiWindows") or item.get("oi") or {}
    score = number(signal.get("score") or item.get("heatScore"), 0)
    alpha_score = (
        score
        + number(source.get("dexHistoryScore"), 0) / 20
        + number(source.get("dexHistoryRepeat"), 0) * 12
        + number(dex_identity.get("historyHits"), 0) * 4
        + number(dex_identity.get("currentHits"), 0) * 9
        + min(number(source.get("xSearchPosts"), 0), 30)
    )
    return {
        "ticker": str(item.get("ticker") or "").upper(),
        "section": item.get("section") or "",
        "stage": item.get("currentStage") or item.get("stage") or item.get("sectionLabel") or "观察",
        "note": item.get("opportunityStructure") or item.get("primaryOpportunityLane") or item.get("why") or "Alpha 映射观察",
        "change24h": market.get("priceChangePercent") or item.get("price24h"),
        "oi1h": oi.get("h1"),
        "heatScore": item.get("heatScore"),
        "alphaScore": round(alpha_score, 1),
        "identityStatus": dex_identity.get("status") or "none",
        "historyHits": dex_identity.get("historyHits") or 0,
        "currentHits": dex_identity.get("currentHits") or 0,
        "xPosts": source.get("xSearchPosts") or 0,
        "dexHits": source.get("dexScreenerHits") or 0,
        "dexRepeat": source.get("dexHistoryRepeat") or 0,
    }


def collect_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for section, rows in dashboard.items():
        if not isinstance(rows, list):
            continue
        for item in rows:
            if not isinstance(item, dict) or not item.get("ticker"):
                continue
            metric = token_metric(item)
            ticker = metric["ticker"]
            if not ticker:
                continue
            existing = by_ticker.get(ticker)
            if existing and existing["alphaScore"] >= metric["alphaScore"]:
                continue
            metric["section"] = section
            by_ticker[ticker] = metric
    tokens = list(by_ticker.values())
    tokens.sort(key=lambda item: (item["identityStatus"] == "verified", item["alphaScore"]), reverse=True)
    return tokens[:16]


def build_payload() -> dict[str, Any]:
    dashboard = load_dashboard()
    sources = dashboard.get("sources") or {}
    counts = dashboard.get("counts") or {}
    tokens = collect_tokens(dashboard)
    verified = [item for item in tokens if item["identityStatus"] == "verified"]
    mapped = sources.get("binanceAlphaCaMappedTickers") or 0
    total = sources.get("binanceAlphaCaTokens") or 0
    coverage = round(number(mapped) / number(total, 1) * 100, 1) if total else 0
    return {
        "app": "悟空",
        "source": "Binance Alpha",
        "mode": "snapshot",
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "alphaFetchedAt": sources.get("binanceAlphaCaFetchedAt"),
        "summary": {
            "tokens": total,
            "mappedTickers": mapped,
            "coveragePct": coverage,
            "cache": sources.get("binanceAlphaCaCache") or "",
            "dexCandidates": counts.get("dexCandidates") or sources.get("dexScreenerCandidates") or 0,
            "repeatCandidates": counts.get("repeatCandidateWatch") or 0,
            "verifiedInWatch": len(verified),
            "topTicker": tokens[0]["ticker"] if tokens else "",
        },
        "tokens": tokens,
        "note": "Alpha 板块展示 Binance Alpha CA 覆盖、DEX/社媒/历史重复映射后的公开观察池，不构成投资建议。",
    }


def main() -> int:
    payload = build_payload()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(f"Wrote Binance Alpha snapshot: {payload['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
