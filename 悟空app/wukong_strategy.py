#!/usr/bin/env python3
"""Shared professional strategy gates for Wukong paper/live preflight.

This module never submits orders. It only ranks, filters, and explains signals.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


MAX_DASHBOARD_AGE_SECONDS = 180
MIN_SCORE = 70
MIN_CONFIRM_SCORE = 70
MIN_QUOTE_VOLUME_USDT = 1_000_000
MIN_OI_H1_PCT = 4.0
MIN_OI_H6_PCT = 8.0
MAX_OI_H6_PCT = 60.0
MIN_PRICE_24H_PCT = -8.0
MAX_PRICE_24H_PCT = 18.0
MIN_FUNDING_RATE = -0.0025
MAX_FUNDING_RATE = 0.0012
HARD_RISK_CODES = {
    "blocked",
    "delist",
    "field_gap",
    "first_sl",
    "late_anchor",
    "observed_only",
    "overheated",
    "replay_risk_veto",
}
WATCH_ONLY_CODES = {"watch_only"}
SOFT_RISK_CODES = {"social_only"}
SIGNAL_SECTIONS = ("entryWindow", "opportunities", "contractLaunch", "earlyEntryRadar")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def dashboard_age_seconds(dashboard: dict[str, Any]) -> float | None:
    generated = parse_time(str(dashboard.get("generatedAt") or ""))
    if not generated:
        return None
    return (datetime.now(timezone.utc) - generated.astimezone(timezone.utc)).total_seconds()


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def token_score(item: dict[str, Any]) -> float:
    signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
    for key in ("score", "primaryOpportunityScore", "heatScore"):
        value = signal.get(key) if key == "score" else item.get(key)
        parsed = number(value)
        if parsed > 0:
            return parsed
    return 0.0


def risk_codes(item: dict[str, Any]) -> set[str]:
    codes = set()
    for value in item.get("visibilityReasonCodes") or []:
        if value:
            codes.add(str(value))
    eligibility = item.get("paperEligibility") or {}
    for value in eligibility.get("reasonCodes") or []:
        if value:
            codes.add(str(value))
    layer = str(item.get("publicLayer") or eligibility.get("layer") or "")
    if layer == "blocked":
        codes.add("blocked")
    if layer == "watch-only":
        codes.add("watch_only")
    return codes


def market(item: dict[str, Any]) -> dict[str, Any]:
    return item.get("market") if isinstance(item.get("market"), dict) else {}


def oi_windows(item: dict[str, Any]) -> dict[str, Any]:
    return market(item).get("oiWindows") if isinstance(market(item).get("oiWindows"), dict) else {}


def strategy_action(item: dict[str, Any]) -> dict[str, Any]:
    strategy = item.get("strategy") if isinstance(item.get("strategy"), dict) else {}
    return strategy.get("action") if isinstance(strategy.get("action"), dict) else {}


def paper_allowed_by_source(item: dict[str, Any]) -> bool:
    eligibility = item.get("paperEligibility") or {}
    if eligibility.get("allowed") is True:
        return True
    automation = str(strategy_action(item).get("automation") or "").lower()
    return automation in {"paper", "paper-only", "auto-paper"}


def evaluate_candidate(item: dict[str, Any], dashboard_fresh: bool) -> dict[str, Any]:
    mkt = market(item)
    oi = oi_windows(item)
    score = token_score(item)
    confirm_score = number(mkt.get("confirmScore"))
    price_24h = number(mkt.get("priceChangePercent"), 999)
    funding = number(mkt.get("fundingRate"))
    quote_volume = number(mkt.get("quoteVolume"))
    oi_h1 = number(oi.get("h1"))
    oi_h6 = number(oi.get("h6"))
    codes = risk_codes(item)
    stage = str(item.get("currentStage") or item.get("stage") or "")
    direction = str(item.get("directionCode") or item.get("direction") or "").upper()
    hard_hits = sorted(codes & HARD_RISK_CODES)
    soft_hits = sorted(codes & SOFT_RISK_CODES)
    reasons: list[str] = []
    warnings: list[str] = []

    if not dashboard_fresh:
        reasons.append("数据超过 180 秒，禁止生成新计划")
    if hard_hits:
        reasons.append(f"硬风险命中：{', '.join(hard_hits)}")
    if codes & WATCH_ONLY_CODES and not paper_allowed_by_source(item):
        reasons.append("来源层级为 watch-only，未允许进入纸交易")
    if not paper_allowed_by_source(item):
        reasons.append("源信号未给出 paperEligibility.allowed")
    if "回避" in stage or str(item.get("currentStageCode") or item.get("stageCode") or "").upper() == "AVOID":
        reasons.append("阶段为回避，不允许开仓")
    if direction and "LONG" not in direction and "偏多" not in direction:
        reasons.append("方向不是偏多")
    if score < MIN_SCORE:
        reasons.append(f"综合分 {score:g} < {MIN_SCORE}")
    if confirm_score < MIN_CONFIRM_SCORE:
        reasons.append(f"确认分 {confirm_score:g} < {MIN_CONFIRM_SCORE}")
    if quote_volume < MIN_QUOTE_VOLUME_USDT:
        reasons.append(f"24h 成交额 {quote_volume:g} < {MIN_QUOTE_VOLUME_USDT:g}")
    if not (MIN_PRICE_24H_PCT <= price_24h <= MAX_PRICE_24H_PCT):
        reasons.append(f"24h 涨跌 {price_24h:g}% 不在 {MIN_PRICE_24H_PCT:g}%..{MAX_PRICE_24H_PCT:g}%")
    if not (MIN_FUNDING_RATE <= funding <= MAX_FUNDING_RATE):
        reasons.append(f"资金费率 {funding:g} 不在 {MIN_FUNDING_RATE:g}..{MAX_FUNDING_RATE:g}")
    if not (oi_h1 >= MIN_OI_H1_PCT or oi_h6 >= MIN_OI_H6_PCT):
        reasons.append(f"OI 未确认：1h {oi_h1:g}% / 6h {oi_h6:g}%")
    if oi_h6 > MAX_OI_H6_PCT:
        reasons.append(f"OI6h {oi_h6:g}% 过热")
    if soft_hits:
        warnings.append(f"软风险提示：{', '.join(soft_hits)}")

    readiness = max(0, min(100, round(
        score * 0.35
        + confirm_score * 0.25
        + min(max(oi_h1, oi_h6), 25) * 1.2
        + min(quote_volume / 1_000_000, 10) * 1.4
        - max(price_24h - 12, 0) * 2
        - len(reasons) * 12
    )))
    return {
        "ticker": str(item.get("ticker") or "").upper(),
        "section": item.get("_signalSection"),
        "stage": stage,
        "score": score,
        "confirmScore": confirm_score,
        "priceChange24hPct": price_24h,
        "fundingRate": funding,
        "quoteVolume": quote_volume,
        "oi1hPct": oi_h1,
        "oi6hPct": oi_h6,
        "readiness": readiness,
        "allowed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "riskCodes": sorted(codes),
    }


def unique_signal_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for section in SIGNAL_SECTIONS:
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


def build_strategy_audit(dashboard: dict[str, Any]) -> dict[str, Any]:
    age = dashboard_age_seconds(dashboard)
    fresh = age is not None and age <= MAX_DASHBOARD_AGE_SECONDS
    tokens = unique_signal_tokens(dashboard)
    evaluations = [evaluate_candidate(item, fresh) for item in tokens]
    allowed = [row for row in evaluations if row["allowed"]]
    allowed.sort(key=lambda row: (row["readiness"], row["score"], row["confirmScore"]), reverse=True)
    rejected = [row for row in evaluations if not row["allowed"]]
    return {
        "dashboardAgeSeconds": round(age, 1) if age is not None else None,
        "dashboardFresh": fresh,
        "rules": {
            "maxDashboardAgeSeconds": MAX_DASHBOARD_AGE_SECONDS,
            "minScore": MIN_SCORE,
            "minConfirmScore": MIN_CONFIRM_SCORE,
            "minQuoteVolumeUsdt": MIN_QUOTE_VOLUME_USDT,
            "oiGate": f"OI1h >= {MIN_OI_H1_PCT:g}% 或 OI6h >= {MIN_OI_H6_PCT:g}%",
            "priceWindow24hPct": [MIN_PRICE_24H_PCT, MAX_PRICE_24H_PCT],
            "fundingWindow": [MIN_FUNDING_RATE, MAX_FUNDING_RATE],
            "hardRiskCodes": sorted(HARD_RISK_CODES),
        },
        "allowed": allowed[:8],
        "rejected": rejected[:16],
        "counts": {
            "candidates": len(tokens),
            "allowed": len(allowed),
            "rejected": len(rejected),
        },
    }
