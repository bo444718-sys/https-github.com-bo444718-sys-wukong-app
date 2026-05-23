#!/usr/bin/env python3
"""Build the Wukong X/Twitter social snapshot.

The app can run immediately from Wukong's existing public snapshot. If an
X/Twitter API Bearer Token is present, it also enriches the file with recent
search results from the official API.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
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
    ROOT / "PWA" / "x_social.json",
    ROOT / "x_social.json",
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/x_social.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/x_social.json"),
]
X_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"
SEARCH_QUERY = "($BTC OR $ETH OR $SOL OR $BNB OR crypto) lang:en -is:retweet"


def load_snapshot() -> dict[str, Any]:
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


def stage_of(item: dict[str, Any]) -> str:
    return str(item.get("currentStage") or item.get("stage") or item.get("sectionLabel") or "观察")


def change_of(item: dict[str, Any]) -> Any:
    market = item.get("market") or {}
    return market.get("priceChangePercent") or item.get("price24h")


def iter_token_cards(dashboard: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cards: list[tuple[str, dict[str, Any]]] = []
    for section, value in dashboard.items():
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict) and item.get("ticker") and isinstance(item.get("sourceBreakdown"), dict):
                cards.append((section, item))
    return cards


def collect_top_tickers(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    by_ticker: dict[str, dict[str, Any]] = {}
    for section, item in iter_token_cards(dashboard):
        ticker = str(item.get("ticker") or "").upper().strip()
        source = item.get("sourceBreakdown") or {}
        posts = int(number(source.get("xSearchPosts"), 0))
        existing = by_ticker.get(ticker)
        if existing and existing["posts"] >= posts:
            continue
        by_ticker[ticker] = {
            "ticker": ticker,
            "posts": posts,
            "section": section,
            "stage": stage_of(item),
            "change24h": change_of(item),
            "heatScore": item.get("heatScore"),
            "note": item.get("opportunityStructure") or item.get("primaryOpportunityLane") or item.get("why") or "X 社媒热度",
            "searchUrl": f"https://x.com/search?q={urllib.parse.quote('$' + ticker + ' crypto')}&src=typed_query&f=live",
        }
    rows = [row for row in by_ticker.values() if row["posts"] > 0]
    rows.sort(key=lambda row: (row["posts"], number(row.get("heatScore"), 0)), reverse=True)
    return rows[:12]


def x_bearer_token() -> str:
    return (
        os.getenv("X_BEARER_TOKEN")
        or os.getenv("TWITTER_BEARER_TOKEN")
        or os.getenv("TWITTER_API_BEARER_TOKEN")
        or ""
    ).strip()


def fetch_recent_x_posts(token: str) -> tuple[list[dict[str, Any]], str]:
    if not token:
        return [], "未配置 X_BEARER_TOKEN，当前使用悟空已有公开快照。"
    params = urllib.parse.urlencode(
        {
            "query": SEARCH_QUERY,
            "max_results": "20",
            "tweet.fields": "created_at,author_id,public_metrics,lang",
        }
    )
    request = urllib.request.Request(
        f"{X_SEARCH_URL}?{params}",
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "WukongXSync/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return [], f"X API HTTP {exc.code}，已回退到悟空快照。"
    except Exception as exc:
        return [], f"X API 暂不可用：{exc}，已回退到悟空快照。"
    tweets = []
    for tweet in payload.get("data") or []:
        metrics = tweet.get("public_metrics") or {}
        tweets.append(
            {
                "id": tweet.get("id"),
                "createdAt": tweet.get("created_at"),
                "text": str(tweet.get("text") or "")[:280],
                "authorId": tweet.get("author_id"),
                "retweets": metrics.get("retweet_count"),
                "likes": metrics.get("like_count"),
                "replies": metrics.get("reply_count"),
                "url": f"https://x.com/i/web/status/{tweet.get('id')}",
            }
        )
    return tweets, "X API v2 recent search 已接入。"


def build_payload() -> dict[str, Any]:
    dashboard = load_snapshot()
    sources = dashboard.get("sources") or {}
    counts = dashboard.get("counts") or {}
    token = x_bearer_token()
    tweets, message = fetch_recent_x_posts(token)
    mode = "x-api-v2" if token and tweets else "snapshot"
    top_tickers = collect_top_tickers(dashboard)
    return {
        "app": "悟空",
        "source": "X / Twitter",
        "mode": mode,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "snapshotFetchedAt": sources.get("xSearchFetchedAt"),
        "summary": {
            "posts": counts.get("xSearchPosts") or sources.get("xSearchPosts") or 0,
            "tickers": sources.get("xSearchTickers") or len(top_tickers),
            "topTicker": top_tickers[0]["ticker"] if top_tickers else "",
            "message": message,
        },
        "topTickers": top_tickers,
        "tweets": tweets,
        "query": SEARCH_QUERY if token else "",
    }


def main() -> int:
    payload = build_payload()
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    for path in OUTPUT_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8")
        except OSError as exc:
            print(f"skip {path}: {exc}", file=sys.stderr)
    print(f"Wrote X social snapshot: {payload['mode']} / {payload['summary']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
