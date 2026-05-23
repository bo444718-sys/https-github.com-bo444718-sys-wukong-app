#!/usr/bin/env python3
"""Telegram control plane for Wukong.

Features:
- Pushes Wukong market/review summaries to Telegram every minute.
- Accepts Telegram commands for refresh, sections, ticker search, watchlist, and AI Q&A.
- Uses only the Python standard library.

Required environment:
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID

Optional environment:
- OPENAI_API_KEY or CODEX_API_KEY
- WUKONG_OPENAI_MODEL, defaults to gpt-4.1-mini
- WUKONG_PUSH_INTERVAL_SECONDS, defaults to 30

When an existing Hermes Telegram gateway is already polling the bot, run this
script with --push-only so it only sends messages and never calls getUpdates.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MICHILL_BASE_URL = "https://michill.ai"
TELEGRAM_LIMIT = 3900
PWA_VERSION = "121"
STATE_PATH = Path(".wukong_telegram_state.json")
SNAPSHOT_PATH = Path("wukong_latest_snapshot.json")
TELEGRAM_STATUS_PATH = Path("telegram_status.json")
PROJECT_ROOT = Path("/Users/wangbo/Documents/New project/悟空app")
ALPHA_PATH = Path("binance_alpha.json")
CONTEXT_PATH = Path("WUKONG_TELEGRAM_BRIDGE.md")
GATE_SYNC_SCRIPT = Path("sync_exchange_api.py")
GATE_PRIVATE_STATUS_SCRIPT = Path("gate_private_status.py")
GATE_TRADE_PREFLIGHT_SCRIPT = Path("gate_trade_preflight.py")
GATE_TRADE_PREFLIGHT_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/gate_trade_preflight.json"),
    PROJECT_ROOT / "PWA" / "gate_trade_preflight.json",
    PROJECT_ROOT / "gate_trade_preflight.json",
    Path("PWA/gate_trade_preflight.json"),
]
PAPER_TRADING_STATE_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/paper_trading_state.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/paper_trading_state.json"),
    PROJECT_ROOT / "PWA" / "paper_trading_state.json",
    PROJECT_ROOT / "paper_trading_state.json",
]
PROFESSIONAL_SYSTEM_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/professional_trade_system.json"),
    Path("/Users/wangbo/.hermes/wukong_telegram/professional_trade_system.json"),
    PROJECT_ROOT / "PWA" / "professional_trade_system.json",
]
QR_SYNC_SCRIPT = Path("generate_download_qr.py")
X_SYNC_SCRIPT = Path("sync_x_api.py")
ALPHA_SYNC_SCRIPT = Path("sync_binance_alpha.py")
HERMES_CHANNEL_DIRECTORY = Path("/Users/wangbo/.hermes/channel_directory.json")
PWA_SNAPSHOT_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/wukong_latest_snapshot.json"),
    PROJECT_ROOT / "PWA" / "wukong_latest_snapshot.json",
    PROJECT_ROOT / "wukong_latest_snapshot.json",
    Path("PWA/wukong_latest_snapshot.json"),
]
PWA_TELEGRAM_STATUS_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/PWA/telegram_status.json"),
    PROJECT_ROOT / "PWA" / "telegram_status.json",
    PROJECT_ROOT / "telegram_status.json",
    Path("PWA/telegram_status.json"),
]
PWA_URL_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt"),
    Path("wukong_pwa_url.txt"),
]


SECTION_LABELS = {
    "entryWindow": "入场窗口",
    "earlyEntryRadar": "早发现雷达",
    "opportunities": "确认/回踩候选",
    "recentSignalChanges": "信号轨迹",
    "oiAnomalyWatch": "OI异动",
    "repeatCandidateWatch": "多次出现",
    "breakoutReview": "启动复盘",
    "delistRiskWatch": "公告风险",
    "overheated": "过热回避",
}


@dataclass
class WukongState:
    offset: int = 0
    chat_id: str = ""
    watchlist: list[str] = field(default_factory=list)
    last_summary_signature: str = ""
    last_signal_signature: str = ""
    last_priority_signature: str = ""

    @classmethod
    def load(cls) -> "WukongState":
        if not STATE_PATH.exists():
            return cls()
        try:
            payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            return cls(
                offset=int(payload.get("offset", 0) or 0),
                chat_id=str(payload.get("chat_id", "") or ""),
                watchlist=[str(item).upper() for item in payload.get("watchlist", [])],
                last_summary_signature=str(payload.get("last_summary_signature", "")),
                last_signal_signature=str(payload.get("last_signal_signature", "")),
                last_priority_signature=str(payload.get("last_priority_signature", "")),
            )
        except Exception:
            return cls()

    def save(self) -> None:
        STATE_PATH.write_text(
            json.dumps(
                {
                    "offset": self.offset,
                    "chat_id": self.chat_id,
                    "watchlist": self.watchlist,
                    "last_summary_signature": self.last_summary_signature,
                    "last_signal_signature": self.last_signal_signature,
                    "last_priority_signature": self.last_priority_signature,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


class HTTPError(RuntimeError):
    pass


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
    extra_headers: dict[str, str] | None = None,
) -> Any:
    data = None
    headers = {"User-Agent": "WukongTelegramBot/1.0"}
    if extra_headers:
        headers.update(extra_headers)
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read()
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise HTTPError(f"{exc.code} {body}") from exc
    except urllib.error.URLError as exc:
        raise HTTPError(str(exc)) from exc


def fetch_dashboard() -> dict[str, Any]:
    return request_json(f"{MICHILL_BASE_URL}/api/summary/public-dashboard")


def sync_wukong_files() -> None:
    script = Path(__file__).resolve().parent / "sync_wukong_files.py"
    if script.exists():
        try:
            env = os.environ.copy()
            env.setdefault("WUKONG_PROJECT_ROOT", "/Users/wangbo/Documents/New project/悟空app")
            subprocess.run([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20, env=env)
        except Exception:
            pass


def fetch_report() -> dict[str, Any] | None:
    try:
        return request_json(f"{MICHILL_BASE_URL}/api/agent-team/public-report")
    except Exception:
        return None


def fetch_calendar() -> dict[str, Any] | None:
    try:
        return request_json(f"{MICHILL_BASE_URL}/api/ai-trading-calendar")
    except Exception:
        return None


def fetch_ticker(ticker: str) -> dict[str, Any]:
    ticker = urllib.parse.quote(ticker.upper())
    return request_json(f"{MICHILL_BASE_URL}/api/summary/ticker/{ticker}")


def current_pwa_url() -> str:
    for path in PWA_URL_PATHS:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except Exception:
            continue
        if value.startswith(("https://", "http://")):
            return value
    return ""


def current_install_url() -> str:
    pwa_url = current_pwa_url().rstrip("/")
    return f"{pwa_url}/install.html?v={PWA_VERSION}" if pwa_url else ""


def refresh_trade_preflight() -> None:
    if GATE_TRADE_PREFLIGHT_SCRIPT.exists():
        try:
            subprocess.run([sys.executable, str(GATE_TRADE_PREFLIGHT_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            pass


def load_trade_preflight() -> dict[str, Any]:
    refresh_trade_preflight()
    for path in GATE_TRADE_PREFLIGHT_PATHS:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {
        "mode": "missing",
        "canSubmitOrder": False,
        "orderEndpointEnabled": False,
        "blockers": ["交易预检文件不存在"],
        "signalTradeGate": {"signalActive": False, "reason": "等待交易预检"},
        "paperTrade": {"enabled": True, "state": "closed", "reason": "等待交易预检", "plan": None},
    }


def load_paper_trading_state() -> dict[str, Any]:
    for path in PAPER_TRADING_STATE_PATHS:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {
        "state": "waiting",
        "positions": [],
        "summary": {"openPositions": 0, "closedTrades": 0, "totalUnrealizedUsdt": 0},
        "realTradingEnabled": False,
        "canSubmitOrder": False,
        "orderEndpointEnabled": False,
    }


def load_professional_system() -> dict[str, Any]:
    for path in PROFESSIONAL_SYSTEM_PATHS:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            return payload
    return {"profile": "waiting", "modules": [], "fileScan": {"count": 0}}


class TelegramClient:
    def __init__(self, token: str, chat_id: str = "") -> None:
        self.token = token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{token}"

    def call(self, method: str, payload: dict[str, Any] | None = None, timeout: int = 35) -> dict[str, Any]:
        result = request_json(f"{self.base_url}/{method}", method="POST", payload=payload or {}, timeout=timeout)
        if not result.get("ok"):
            raise HTTPError(json.dumps(result, ensure_ascii=False))
        return result

    def get_me(self) -> dict[str, Any]:
        return self.call("getMe")

    def get_updates(self, offset: int, timeout: int = 25) -> list[dict[str, Any]]:
        payload = {
            "offset": offset,
            "timeout": timeout,
            "allowed_updates": ["message", "callback_query"],
        }
        return self.call("getUpdates", payload=payload, timeout=timeout + 10).get("result", [])

    def answer_callback(self, callback_query_id: str, text: str = "已收到") -> None:
        self.call("answerCallbackQuery", {"callback_query_id": callback_query_id, "text": text}, timeout=10)

    def send(self, text: str, *, reply_markup: dict[str, Any] | None = None, chat_id: str | None = None) -> list[dict[str, Any]]:
        target_chat_id = chat_id or self.chat_id
        if not target_chat_id:
            raise HTTPError("TELEGRAM_CHAT_ID is not configured yet. Send /start to the bot to auto-bind this chat.")
        chunks = split_message(text)
        results: list[dict[str, Any]] = []
        for index, chunk in enumerate(chunks):
            payload: dict[str, Any] = {
                "chat_id": target_chat_id,
                "text": chunk,
                "disable_web_page_preview": True,
            }
            if reply_markup and index == len(chunks) - 1:
                payload["reply_markup"] = reply_markup
            results.append(self.call("sendMessage", payload=payload, timeout=20))
        return results


def split_message(text: str) -> list[str]:
    if len(text) <= TELEGRAM_LIMIT:
        return [text]
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in text.splitlines():
        extra = len(line) + 1
        if current and current_len + extra > TELEGRAM_LIMIT:
            chunks.append("\n".join(current))
            current = [line]
            current_len = extra
        else:
            current.append(line)
            current_len += extra
    if current:
        chunks.append("\n".join(current))
    return chunks


def keyboard() -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "刷新", "callback_data": "/refresh"},
                {"text": "入场窗口", "callback_data": "/section entryWindow"},
            ],
            [
                {"text": "入场币种", "callback_data": "/entry"},
                {"text": "合约启动", "callback_data": "/contract"},
            ],
            [
                {"text": "可操作", "callback_data": "/signals"},
                {"text": "下一步", "callback_data": "/next"},
            ],
            [
                {"text": "优先级", "callback_data": "/priority"},
                {"text": "我的关注", "callback_data": "/watch list"},
            ],
            [
                {"text": "纸交易", "callback_data": "/paper"},
                {"text": "实盘确认", "callback_data": "/confirm_live"},
            ],
            [
                {"text": "早发现", "callback_data": "/section earlyEntryRadar"},
                {"text": "确认候选", "callback_data": "/section opportunities"},
            ],
            [
                {"text": "Alpha", "callback_data": "/alpha"},
                {"text": "风险区", "callback_data": "/risk"},
            ],
            [
                {"text": "帮助", "callback_data": "/help"},
            ],
        ]
    }


def ticker_keyboard(dashboard: dict[str, Any]) -> dict[str, Any]:
    tickers: list[str] = []
    for item in entry_tokens(dashboard)[:6] + contract_launch_tokens(dashboard)[:6]:
        ticker = str(item.get("ticker") or "").upper()
        if ticker and ticker not in tickers:
            tickers.append(ticker)
    rows = []
    for index in range(0, len(tickers), 3):
        rows.append([
            {"text": ticker, "callback_data": f"/search {ticker}"}
            for ticker in tickers[index : index + 3]
        ])
    rows.extend(keyboard()["inline_keyboard"])
    return {"inline_keyboard": rows}


def confirm_keyboard() -> dict[str, Any]:
    rows = [
        [
            {"text": "刷新预检", "callback_data": "/confirm_live"},
            {"text": "纸交易计划", "callback_data": "/paper"},
        ],
        [
            {"text": "下一步", "callback_data": "/next"},
            {"text": "风险区", "callback_data": "/risk"},
        ],
    ]
    return {"inline_keyboard": rows}


def auto_watch_signal_tokens(dashboard: dict[str, Any], state: WukongState) -> list[str]:
    added: list[str] = []
    for item in entry_tokens(dashboard)[:12] + contract_launch_tokens(dashboard)[:24]:
        ticker = str(item.get("ticker") or "").upper()
        if ticker and ticker not in state.watchlist:
            state.watchlist.insert(0, ticker)
            added.append(ticker)
    if added:
        state.watchlist = state.watchlist[:120]
        state.save()
    return added


def fmt_time(value: str | None) -> str:
    if not value:
        return "暂无"
    try:
        cleaned = value.replace("Z", "+00:00")
        dt = datetime.fromisoformat(cleaned)
        return dt.astimezone().strftime("%m-%d %H:%M")
    except Exception:
        return value[:16]


def fmt_pct(value: Any) -> str:
    try:
        return f"{float(value):+.1f}%"
    except Exception:
        return "--"


def fmt_num(value: Any) -> str:
    try:
        number = float(value)
    except Exception:
        return "--"
    if abs(number) >= 1_000_000_000:
        return f"{number / 1_000_000_000:.1f}B"
    if abs(number) >= 1_000_000:
        return f"{number / 1_000_000:.1f}M"
    if abs(number) >= 1_000:
        return f"{number / 1_000:.1f}K"
    return f"{number:.0f}"


def token_line(item: dict[str, Any], rank: int) -> str:
    market = item.get("market") or {}
    signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
    oi = market.get("oiWindows") or item.get("oi") or {}
    stage = item.get("currentStage") or item.get("stage") or "观察"
    structure = item.get("opportunityStructure") or item.get("primaryOpportunityLane") or "信号"
    price = market.get("markPrice") or item.get("price")
    return (
        f"{rank}. {item.get('ticker', '--')} | {stage} | {structure}\n"
        f"   24h {fmt_pct(market.get('priceChangePercent') or item.get('price24h'))} · "
        f"OI1h {fmt_pct(oi.get('h1'))} · OI6h {fmt_pct(oi.get('h6'))} · "
        f"费率 {market.get('fundingRate') or item.get('fundingRate') or '--'} · "
        f"分 {signal.get('score', item.get('heatScore', '--'))} · 价 {price or '--'}"
    )


def is_contract_launch(item: dict[str, Any]) -> bool:
    values = [
        item.get("opportunityStructure"),
        item.get("primaryOpportunityLane"),
        item.get("currentStage"),
        item.get("stage"),
        item.get("why"),
        item.get("sectionLabel"),
    ]
    text = " ".join(str(value) for value in values if value)
    return "合约启动" in text or ("合约" in text and "启动" in text)


def unique_tokens(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for item in items:
        ticker = str(item.get("ticker") or "").upper()
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        rows.append(item)
    return rows


def entry_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    return unique_tokens((dashboard.get("entryWindow") or []) + (dashboard.get("opportunities") or []))


def contract_launch_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in [
        "entryWindow",
        "earlyEntryRadar",
        "opportunities",
        "marketWatch",
        "risingAttention",
        "riskWinnersReview",
        "recentSignalChanges",
    ]:
        rows = dashboard.get(section)
        if isinstance(rows, list):
            items.extend(item for item in rows if isinstance(item, dict) and is_contract_launch(item))
    return unique_tokens(items)


def action_bucket(item: dict[str, Any]) -> str:
    stage = str(item.get("currentStage") or item.get("stage") or "")
    structure = str(item.get("opportunityStructure") or item.get("primaryOpportunityLane") or "")
    text = f"{stage} {structure}"
    if "回避" in text or "高位风险" in text or "过热" in text:
        return "回避/风险"
    if "小仓试错" in text:
        return "小仓试错"
    if "重点候选" in text:
        return "重点候选"
    if "等待回踩" in text:
        return "等待回踩"
    return "观察"


def bucket_tokens(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    buckets = {label: [] for label in ["小仓试错", "重点候选", "等待回踩", "观察", "回避/风险"]}
    for item in items:
        buckets.setdefault(action_bucket(item), []).append(item)
    return buckets


def actionable_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    items = entry_tokens(dashboard) + contract_launch_tokens(dashboard)
    return [
        item
        for item in unique_tokens(items)
        if action_bucket(item) in {"小仓试错", "重点候选", "等待回踩"}
    ]


def signal_score(item: dict[str, Any]) -> float:
    market = item.get("market") or {}
    signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
    oi = market.get("oiWindows") or item.get("oi") or {}
    bucket_weight = {"小仓试错": 30, "重点候选": 24, "等待回踩": 18}.get(action_bucket(item), 0)
    try:
        base = float(signal.get("score") or item.get("heatScore") or 0)
    except Exception:
        base = 0
    try:
        oi_score = max(min(float(oi.get("h1") or 0), 20), -20)
    except Exception:
        oi_score = 0
    return bucket_weight + base + oi_score


def build_summary(dashboard: dict[str, Any], report: dict[str, Any] | None, calendar: dict[str, Any] | None) -> str:
    counts = dashboard.get("counts") or {}
    report_counts = (report or {}).get("counts") or {}
    public_report = (report or {}).get("publicReport") or {}
    lines = [
        "悟空实时摘要",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        f"App推送：{datetime.now().strftime('%m-%d %H:%M:%S')}",
        "",
        f"币种数：{counts.get('tickers', 0)}",
        f"入场窗口：{counts.get('entryWindow', 0)}",
        f"早发现雷达：{counts.get('earlyEntryRadar', 0)}",
        f"确认/回踩候选：{len(dashboard.get('opportunities') or [])}",
        f"OI异动：{counts.get('oiAnomalyWatch', 0)}",
        f"风险样本：{counts.get('delistRiskBlocked', 0) + len(dashboard.get('overheated') or [])}",
    ]
    sources = dashboard.get("sources") or {}
    if sources.get("binanceAlphaCaTokens"):
        lines.append(
            f"Binance Alpha：CA {sources.get('binanceAlphaCaTokens')} · 已映射 {sources.get('binanceAlphaCaMappedTickers', 0)}"
        )
    if calendar:
        lines.append(f"AI纸面日历：{fmt_pct(calendar.get('totalReturnPct'))} · {calendar.get('totalTrades', 0)}笔")
    if report_counts:
        lines.extend(
            [
                "",
                f"AI复盘：进入视野 {report_counts.get('appearedToday', 0)} · 可复盘 {report_counts.get('trustedReturns', 0)} · 涨超30% {report_counts.get('hit30', 0)}",
            ]
        )
    if public_report.get("headline"):
        lines.extend(["", public_report["headline"]])
    entry_rows = entry_tokens(dashboard)
    contract_rows = contract_launch_tokens(dashboard)
    lines.extend(["", f"入场币种 Top {min(8, len(entry_rows))}"])
    for index, item in enumerate(entry_rows[:8], 1):
        lines.append(token_line(item, index))
    lines.extend(["", f"合约启动币种 Top {min(8, len(contract_rows))}"])
    for index, item in enumerate(contract_rows[:8], 1):
        lines.append(token_line(item, index))
    install_url = current_install_url()
    if install_url:
        lines.extend(["", f"iPhone安装：{install_url}"])
    lines.extend(["", "操作：/help 查看 Telegram 指令。"])
    return "\n".join(lines)


def queue_counts(dashboard: dict[str, Any]) -> dict[str, int]:
    risks = (dashboard.get("delistRiskWatch") or []) + (dashboard.get("overheated") or [])
    return {
        "entry": len(entry_tokens(dashboard)),
        "contractLaunch": len(contract_launch_tokens(dashboard)),
        "priority": min(5, len(actionable_tokens(dashboard))),
        "risk": len(unique_tokens(risks)),
    }


def write_telegram_status(
    *,
    dashboard: dict[str, Any] | None,
    status: str,
    mode: str,
    chat_id: str,
    sent_types: list[str] | None = None,
    message_chunks: int = 0,
    error: str = "",
) -> None:
    counts = queue_counts(dashboard or {}) if dashboard else {"entry": 0, "contractLaunch": 0, "priority": 0, "risk": 0}
    payload = {
        "app": "悟空",
        "status": status,
        "mode": mode,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "marketGeneratedAt": (dashboard or {}).get("generatedAt"),
        "chatIdMasked": f"...{str(chat_id)[-4:]}" if chat_id else "",
        "sentTypes": sent_types or [],
        "messageChunks": message_chunks,
        "queueCounts": counts,
        "queueTotal": sum(counts.values()),
        "error": error,
    }
    paths = [TELEGRAM_STATUS_PATH, *PWA_TELEGRAM_STATUS_PATHS]
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            continue


def write_snapshot(
    *,
    dashboard: dict[str, Any],
    report: dict[str, Any] | None,
    calendar: dict[str, Any] | None,
    summary: str,
    mode: str,
) -> None:
    payload = {
        "app": "悟空",
        "mode": mode,
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "sourceGeneratedAt": dashboard.get("generatedAt"),
        "summary": summary,
        "dashboard": dashboard,
        "report": report,
        "calendar": calendar,
    }
    encoded = json.dumps(payload, ensure_ascii=False, indent=2)
    SNAPSHOT_PATH.write_text(encoded, encoding="utf-8")
    for path in PWA_SNAPSHOT_PATHS:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(encoded, encoding="utf-8")
        except OSError:
            pass
    if GATE_SYNC_SCRIPT.exists():
        subprocess.run([sys.executable, str(GATE_SYNC_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if GATE_PRIVATE_STATUS_SCRIPT.exists():
        subprocess.run([sys.executable, str(GATE_PRIVATE_STATUS_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if QR_SYNC_SCRIPT.exists():
        subprocess.run([sys.executable, str(QR_SYNC_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if X_SYNC_SCRIPT.exists():
        subprocess.run([sys.executable, str(X_SYNC_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    if ALPHA_SYNC_SCRIPT.exists():
        subprocess.run([sys.executable, str(ALPHA_SYNC_SCRIPT)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)


def write_bridge_context(push_interval: int) -> None:
    CONTEXT_PATH.write_text(
        "\n".join(
            [
                "# 悟空 Telegram / Codex Bridge",
                "",
                "这个目录是悟空 Apple App 和现有 Telegram/Codex 机器人的共享工作区。",
                "",
                f"- 悟空推送模式：push-only，不调用 Telegram getUpdates。",
                f"- 推送频率：每 {push_interval} 秒。",
                "- 最新快照：`wukong_latest_snapshot.json`。",
                "- Telegram 接收和继续操作由现有 Hermes/Codex 网关负责。",
                "",
                "当用户在 Telegram 里要求操作悟空时，优先读取 `wukong_latest_snapshot.json`，再根据用户问题给出摘要、风险、候选列表或下一步动作。",
                "所有内容只作为公开研究信号与复盘，不构成投资建议。",
                "",
            ]
        ),
        encoding="utf-8",
    )


def build_section(dashboard: dict[str, Any], section: str, limit: int = 12) -> str:
    items = dashboard.get(section) or []
    label = SECTION_LABELS.get(section, section)
    if not items:
        return f"悟空 · {label}\n当前没有可显示的数据。"
    lines = [f"悟空 · {label}", f"数量：{len(items)}", ""]
    for index, item in enumerate(items[:limit], 1):
        lines.append(token_line(item, index))
    return "\n".join(lines)


def build_entry_tokens(dashboard: dict[str, Any]) -> str:
    items = entry_tokens(dashboard)
    if not items:
        return "悟空 · 入场币种\n当前没有入场币种。"
    lines = ["悟空 · 入场币种", f"数量：{len(items)}", ""]
    for index, item in enumerate(items[:16], 1):
        lines.append(token_line(item, index))
    return "\n".join(lines)


def build_contract_launch(dashboard: dict[str, Any]) -> str:
    items = contract_launch_tokens(dashboard)
    if not items:
        return "悟空 · 合约启动币种\n当前没有合约启动币种。"
    lines = ["悟空 · 合约启动币种", f"数量：{len(items)}", ""]
    for index, item in enumerate(items[:18], 1):
        lines.append(token_line(item, index))
    return "\n".join(lines)


def build_actionable_signals(dashboard: dict[str, Any]) -> str:
    items = actionable_tokens(dashboard)
    if not items:
        return "悟空 · 可操作信号\n当前没有小仓试错、重点候选或等待回踩。"
    buckets = bucket_tokens(items)
    lines = [
        "悟空 · 可操作信号",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        f"数量：{len(items)}",
        "",
    ]
    rank = 1
    for label in ["小仓试错", "重点候选", "等待回踩"]:
        rows = buckets.get(label) or []
        if not rows:
            continue
        lines.append(f"{label}：{len(rows)}")
        for item in rows[:8]:
            lines.append(token_line(item, rank))
            rank += 1
        lines.append("")
    lines.append("说明：这里只过滤掉回避/高位风险；仍只做公开研究信号，不构成投资建议。")
    return "\n".join(lines).strip()


def next_action_for(item: dict[str, Any]) -> str:
    bucket = action_bucket(item)
    market = item.get("market") or {}
    oi = market.get("oiWindows") or item.get("oi") or {}
    change = fmt_pct(market.get("priceChangePercent") or item.get("price24h"))
    oi1h = fmt_pct(oi.get("h1"))
    funding = market.get("fundingRate") or item.get("fundingRate") or "--"
    ticker = item.get("ticker", "--")
    structure = item.get("opportunityStructure") or item.get("primaryOpportunityLane") or "信号"
    if bucket == "小仓试错":
        action = "只允许小仓纸面观察；等 5m/15m 不破位、OI 不突然反抽过热，再复核。"
    elif bucket == "重点候选":
        action = "优先观察回踩承接；等价格稳住且资金费率不过热，再进入下一轮复核。"
    elif bucket == "等待回踩":
        action = "不追高；等回踩、量能缩回后重新放量，再看是否升级。"
    else:
        action = "只观察，不升级。"
    return (
        f"{ticker} | {bucket} | {structure}\n"
        f"   现状：24h {change} · OI1h {oi1h} · 费率 {funding}\n"
        f"   下一步：{action}"
    )


def build_next_actions(dashboard: dict[str, Any]) -> str:
    items = actionable_tokens(dashboard)
    if not items:
        return "悟空 · 下一步动作\n当前没有可操作观察。"
    buckets = bucket_tokens(items)
    lines = [
        "悟空 · 下一步动作",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        "只做公开研究信号，不构成投资建议。",
        "",
    ]
    for label in ["小仓试错", "重点候选", "等待回踩"]:
        rows = buckets.get(label) or []
        if not rows:
            continue
        lines.append(f"{label}")
        for item in rows[:6]:
            lines.append(next_action_for(item))
        lines.append("")
    lines.append("快捷：点币种按钮查详情；/signals 看分层列表。")
    return "\n".join(lines).strip()


def build_priority_signals(dashboard: dict[str, Any], limit: int = 5) -> str:
    items = sorted(actionable_tokens(dashboard), key=signal_score, reverse=True)
    if not items:
        return "悟空 · 优先级\n当前没有可优先观察的信号。"
    rows = items[:limit]
    lines = [
        "悟空 · 优先级",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        "排序：阶段权重 + 信号分 + OI1h，只做研究观察。",
        "",
    ]
    for index, item in enumerate(rows, 1):
        lines.append(token_line(item, index))
        lines.append(f"   下一步：{next_action_for(item).split('下一步：', 1)[-1]}")
    lines.append("")
    lines.append("指令：/next 看完整动作，/signals 看分层列表。")
    return "\n".join(lines)


def priority_tokens(dashboard: dict[str, Any], limit: int = 5) -> list[dict[str, Any]]:
    return sorted(actionable_tokens(dashboard), key=signal_score, reverse=True)[:limit]


def priority_signature(dashboard: dict[str, Any]) -> str:
    rows = priority_tokens(dashboard)
    return json.dumps(
        {
            "generatedAt": dashboard.get("generatedAt"),
            "priority": [item.get("ticker") for item in rows],
            "scores": [round(signal_score(item), 2) for item in rows],
        },
        ensure_ascii=False,
    )


def build_priority_change_alert(dashboard: dict[str, Any]) -> str:
    rows = priority_tokens(dashboard)
    if not rows:
        return "悟空 · 优先级变化\n当前没有优先级候选。"
    lines = [
        "悟空 · 优先级变化",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        "Top 5 已刷新：",
        "",
    ]
    for index, item in enumerate(rows, 1):
        lines.append(f"{index}. {item.get('ticker', '--')} · {action_bucket(item)} · 分 {round(signal_score(item), 1)}")
    lines.extend(["", "指令：/priority 看完整优先级，/next 看下一步动作。"])
    return "\n".join(lines)


def signal_signature(dashboard: dict[str, Any]) -> str:
    return json.dumps(
        {
            "generatedAt": dashboard.get("generatedAt"),
            "entry": [item.get("ticker") for item in entry_tokens(dashboard)],
            "contract": [item.get("ticker") for item in contract_launch_tokens(dashboard)],
        },
        ensure_ascii=False,
    )


def build_signal_alert(dashboard: dict[str, Any]) -> str:
    entry_rows = entry_tokens(dashboard)
    contract_rows = contract_launch_tokens(dashboard)
    actionable_rows = actionable_tokens(dashboard)
    lines = [
        "悟空 · 入场/合约启动同步",
        f"行情生成：{fmt_time(dashboard.get('generatedAt'))}",
        f"入场币种：{len(entry_rows)} 个",
        f"合约启动：{len(contract_rows)} 个",
        f"可操作观察：{len(actionable_rows)} 个",
        "",
        "可操作观察",
    ]
    if actionable_rows:
        for index, item in enumerate(actionable_rows[:10], 1):
            lines.append(token_line(item, index))
    else:
        lines.append("暂无")
    lines.extend(["", "入场币种"])
    if entry_rows:
        for index, item in enumerate(entry_rows[:8], 1):
            lines.append(token_line(item, index))
    else:
        lines.append("暂无")
    lines.extend(["", "合约启动币种"])
    if contract_rows:
        for index, item in enumerate(contract_rows[:10], 1):
            lines.append(token_line(item, index))
    else:
        lines.append("暂无")
    lines.extend(["", "指令：/signals 查看过滤后的可操作信号，/entry 查看全部入场，/contract 查看全部合约启动。"])
    return "\n".join(lines)


def build_signal_alert_with_watch(dashboard: dict[str, Any], added: list[str]) -> str:
    text = build_signal_alert(dashboard)
    if added:
        text += "\n\n已自动加入关注：" + "、".join(added[:24])
    return text


def build_risk(dashboard: dict[str, Any]) -> str:
    lines = ["悟空 · 风险区", ""]
    for section in ["delistRiskWatch", "overheated"]:
        lines.append(f"{SECTION_LABELS[section]}：")
        items = dashboard.get(section) or []
        if not items:
            lines.append("暂无")
        for index, item in enumerate(items[:8], 1):
            lines.append(token_line(item, index))
        lines.append("")
    return "\n".join(lines).strip()


def build_alpha() -> str:
    try:
        alpha = json.loads(ALPHA_PATH.read_text(encoding="utf-8"))
    except Exception:
        return "悟空 · Binance Alpha\nAlpha 快照还在生成中，请稍后 /refresh。"
    summary = alpha.get("summary") or {}
    lines = [
        "悟空 · Binance Alpha",
        f"更新时间：{fmt_time(alpha.get('updatedAt'))}",
        f"Alpha CA：{summary.get('tokens', 0)}",
        f"已映射：{summary.get('mappedTickers', 0)} · 覆盖率 {summary.get('coveragePct', 0)}%",
        f"DEX候选：{summary.get('dexCandidates', 0)} · 反复候选 {summary.get('repeatCandidates', 0)}",
        "",
        "Alpha 观察 Top 8",
    ]
    for index, item in enumerate((alpha.get("tokens") or [])[:8], 1):
        lines.append(
            f"{index}. {item.get('ticker', '--')} | {item.get('stage', '观察')} | Alpha分 {item.get('alphaScore', '--')}\n"
            f"   24h {fmt_pct(item.get('change24h'))} · OI1h {fmt_pct(item.get('oi1h'))} · "
            f"身份 {item.get('identityStatus', 'none')} · 历史 {item.get('historyHits', 0)}"
        )
    lines.extend(["", "说明：Alpha 板块只做公开观察和复盘，不构成投资建议。"])
    return "\n".join(lines)


def build_ticker_report(result: dict[str, Any]) -> str:
    ticker = result.get("ticker", "--")
    if not result.get("found"):
        return f"悟空搜索：{ticker}\n暂未在公开池子里出现。"
    appearances = result.get("appearances") or []
    lines = [f"悟空搜索：{ticker}", f"出现记录：{len(appearances)}", ""]
    for index, item in enumerate(appearances[:12], 1):
        lines.append(token_line(item, index))
        if item.get("nextAction"):
            lines.append(f"   下一步：{item['nextAction']}")
    return "\n".join(lines)


def normalize_ticker(value: str) -> str:
    return value.strip().upper().replace("$", "").replace("#", "").replace("USDT", "")


def build_watchlist(dashboard: dict[str, Any], state: WukongState) -> str:
    if not state.watchlist:
        return "悟空关注列表为空。使用 /watch add APT 添加。"
    by_ticker = {str(item.get("ticker", "")).upper(): item for item in collect_all_tokens(dashboard)}
    lines = ["悟空 · 我的关注", ""]
    for index, ticker in enumerate(state.watchlist, 1):
        item = by_ticker.get(ticker)
        if item:
            lines.append(token_line(item, index))
        else:
            lines.append(f"{index}. {ticker} | 当前摘要中暂无完整卡片，可用 /search {ticker}")
    return "\n".join(lines)


def collect_all_tokens(dashboard: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for key in SECTION_LABELS:
        section_items = dashboard.get(key)
        if isinstance(section_items, list):
            items.extend(item for item in section_items if isinstance(item, dict))
    return items


def ai_answer(question: str, dashboard: dict[str, Any], report: dict[str, Any] | None) -> str:
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CODEX_API_KEY")
    if not api_key:
        return "还没有配置 OPENAI_API_KEY 或 CODEX_API_KEY，无法使用 Codex/OpenAI 问答。"
    model = os.getenv("WUKONG_OPENAI_MODEL", "gpt-4.1-mini")
    context = {
        "generatedAt": dashboard.get("generatedAt"),
        "counts": dashboard.get("counts"),
        "entryWindow": compact_tokens(dashboard.get("entryWindow") or []),
        "earlyEntryRadar": compact_tokens(dashboard.get("earlyEntryRadar") or []),
        "opportunities": compact_tokens(dashboard.get("opportunities") or []),
        "risk": compact_tokens((dashboard.get("delistRiskWatch") or []) + (dashboard.get("overheated") or [])),
        "publicReport": (report or {}).get("publicReport", {}),
    }
    prompt = (
        "你是悟空 Telegram 控制台。只根据提供的公开市场摘要回答，"
        "不要给确定性投资建议，不要说保证收益，不要让用户重仓。"
        "回答要短，给可观察点、风险和下一步查看命令。\n\n"
        f"问题：{question}\n\n"
        f"公开数据：{json.dumps(context, ensure_ascii=False)[:12000]}"
    )
    payload = {
        "model": model,
        "input": prompt,
        "max_output_tokens": 700,
    }
    try:
        result = request_json(
            "https://api.openai.com/v1/responses",
            method="POST",
            payload=payload,
            timeout=45,
            extra_headers={"Authorization": f"Bearer {api_key}"},
        )
    except HTTPError as exc:
        return f"Codex/OpenAI API 调用失败：{exc}"
    return extract_response_text(result) or "Codex/OpenAI API 没有返回文本。"


def compact_tokens(items: list[dict[str, Any]], limit: int = 12) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in items[:limit]:
        market = item.get("market") or {}
        signal = item.get("entryWindowSignal") or item.get("earlyEntrySignal") or {}
        compact.append(
            {
                "ticker": item.get("ticker"),
                "stage": item.get("currentStage") or item.get("stage"),
                "structure": item.get("opportunityStructure") or item.get("primaryOpportunityLane"),
                "price24h": market.get("priceChangePercent") or item.get("price24h"),
                "fundingRate": market.get("fundingRate") or item.get("fundingRate"),
                "score": signal.get("score") or item.get("heatScore"),
                "why": item.get("nextAction") or item.get("why") or item.get("reason"),
            }
        )
    return compact


def extract_response_text(result: dict[str, Any]) -> str:
    if isinstance(result.get("output_text"), str):
        return result["output_text"].strip()
    texts: list[str] = []
    for item in result.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                texts.append(str(content["text"]))
    return "\n".join(texts).strip()


def format_tp_tiers(tiers: list[dict[str, Any]]) -> str:
    parts = []
    for index, tier in enumerate(tiers, 1):
        trigger = tier.get("triggerPct", tier.get("pct", "--"))
        close = tier.get("closePct", tier.get("close", "--"))
        parts.append(f"第{index}档 +{trigger}% 平 {close}%")
    return "；".join(parts) if parts else "--"


def build_paper_trade_message() -> str:
    preflight = load_trade_preflight()
    engine = load_paper_trading_state()
    gate = preflight.get("signalTradeGate") or {}
    paper = preflight.get("paperTrade") or {}
    plan = paper.get("plan") or {}
    risk = preflight.get("riskBudget") or {}
    positions = engine.get("positions") or []
    summary = engine.get("summary") or {}
    lines = [
        "悟空 · 自动纸交易",
        f"状态：{engine.get('state') or paper.get('state', '--')}",
        f"信号：{'存在' if gate.get('signalActive') else '消失'}",
        f"说明：{paper.get('reason') or gate.get('reason') or '--'}",
        f"开仓数：{summary.get('openPositions', 0)} · 已平仓：{summary.get('closedTrades', 0)} · 浮盈亏：{summary.get('totalUnrealizedUsdt', 0)}U",
        "",
    ]
    if positions:
        lines.append("当前纸仓：")
        for item in positions[:5]:
            lines.append(
                f"- {item.get('market', '--')} {item.get('side', '--')} | 入 {item.get('entryPrice', '--')} / 现 {item.get('lastPrice', '--')} | {item.get('unrealizedPct', 0)}% · {item.get('unrealizedUsdt', 0)}U"
            )
        lines.append("")
    if plan:
        lines.extend(
            [
                f"标的：{plan.get('market', '--')}",
                f"方向：{plan.get('side', '--')}",
                f"杠杆：{plan.get('leverage', risk.get('leverage', '--'))}x",
                f"保证金：{plan.get('maxMarginUsdt', risk.get('maxMarginUsdt', '--'))}U",
                f"名义仓位：{plan.get('maxNotionalUsdt', risk.get('maxNotionalUsdt', '--'))}U",
                f"单笔风险封顶：{plan.get('riskPerTradeUsdt', risk.get('riskPerTradeUsdt', '--'))}U",
                f"止损：基础 {plan.get('stopLossPct', '--')}%，最多 {plan.get('maxStopLossPct', '--')}%",
                f"止盈：{format_tp_tiers(plan.get('takeProfitTiers') or [])}",
                "",
                "自动规则：信号出现自动生成纸交易；信号消失自动关闭纸交易计划。",
            ]
        )
    else:
        lines.append("当前没有入仓信号，纸交易计划已关闭。")
    lines.extend(
        [
            "",
            "真实订单：未提交。",
            "操作：/confirm_live 查看一键实盘确认预检。",
        ]
    )
    return "\n".join(lines)


def build_confirm_live_message() -> str:
    preflight = load_trade_preflight()
    system = load_professional_system()
    gate = preflight.get("signalTradeGate") or {}
    confirm = preflight.get("telegramConfirm") or {}
    blockers = preflight.get("blockers") or []
    readiness = preflight.get("manualLiveReadiness") or []
    paper = preflight.get("paperTrade") or {}
    plan = paper.get("plan") or {}
    lines = [
        "悟空 · Telegram 一键实盘确认",
        "",
        "当前模式：预检，不提交 Gate 订单",
        f"信号闸门：{gate.get('reason', '--')}",
        f"确认入口：{confirm.get('state', 'preflight-only')}",
        f"系统档案：{system.get('profile', 'waiting')} · 文件 {((system.get('fileScan') or {}).get('count', 0))}",
        f"订单提交：{'允许' if preflight.get('canSubmitOrder') else '禁止'}",
        f"订单端点：{'开启' if preflight.get('orderEndpointEnabled') else '关闭'}",
        "",
    ]
    if plan:
        lines.extend(
            [
                f"待确认纸交易计划：{plan.get('market', '--')}",
                f"保证金/名义：{plan.get('maxMarginUsdt', '--')}U / {plan.get('maxNotionalUsdt', '--')}U",
                f"止损：{plan.get('stopLossPct', '--')}%-{plan.get('maxStopLossPct', '--')}%",
                "",
            ]
        )
    if blockers:
        lines.append("阻断项：")
        lines.extend([f"- {item}" for item in blockers])
        lines.append("")
    modules = system.get("modules") or []
    if modules:
        lines.append("专业模块：")
        for item in modules[:8]:
            lines.append(f"- {'OK' if item.get('ready') else 'LOCK'} {item.get('name', '--')}：{item.get('state', '--')}")
        lines.append("")
    lines.append("准入清单：")
    if readiness:
        for item in readiness:
            lines.append(f"- {'OK' if item.get('ok') else 'NO'} {item.get('name', '--')}：{item.get('detail', '--')}")
    else:
        lines.append("- 等待后端预检")
    lines.extend(
        [
            "",
            "结论：这是 Telegram 一键确认的安全预检版。通过所有准入项之前，不会发送真实订单。",
        ]
    )
    return "\n".join(lines)


def help_text() -> str:
    return "\n".join(
        [
            "悟空 Telegram 指令",
            "",
            "/summary 发送实时摘要",
            "/refresh 立即刷新并发送摘要",
            "/priority 查看最高优先级",
            "/next 查看下一步动作",
            "/signals 查看过滤后的可操作信号",
            "/entry 查看入场币种",
            "/contract 查看合约启动币种",
            "/paper 查看自动纸交易计划",
            "/confirm_live 查看 Telegram 一键实盘确认预检",
            "/section entryWindow 查看入场窗口",
            "/section earlyEntryRadar 查看早发现雷达",
            "/section opportunities 查看确认/回踩候选",
            "/section oiAnomalyWatch 查看 OI 异动",
            "/alpha 查看 Binance Alpha 板块",
            "/risk 查看风险区",
            "/search APT 搜索币种轨迹",
            "/watch add APT 添加关注",
            "/watch remove APT 移除关注",
            "/watch list 查看关注",
            "/ask 现在最值得观察的三个币是什么？ 调用 Codex/OpenAI API 分析",
            "",
            "说明：所有内容只做公开研究信号和复盘，不构成投资建议。",
        ]
    )


def handle_command(text: str, state: WukongState) -> tuple[str, dict[str, Any] | None]:
    parts = text.strip().split()
    command = parts[0].lower() if parts else "/help"
    if command in {"/paper", "/paper_trade", "/papertrade"}:
        return build_paper_trade_message(), confirm_keyboard()
    if command in {"/confirm_live", "/confirm", "/live_confirm"}:
        return build_confirm_live_message(), confirm_keyboard()
    dashboard = fetch_dashboard()
    report = fetch_report()

    if command in {"/start", "/help"}:
        return help_text(), keyboard()
    if command in {"/summary", "/refresh"}:
        return build_summary(dashboard, report, fetch_calendar()), keyboard()
    if command in {"/priority", "/top"}:
        return build_priority_signals(dashboard), ticker_keyboard(dashboard)
    if command in {"/next", "/nextstep"}:
        return build_next_actions(dashboard), ticker_keyboard(dashboard)
    if command in {"/signals", "/signal"}:
        return build_actionable_signals(dashboard), ticker_keyboard(dashboard)
    if command == "/entry":
        return build_entry_tokens(dashboard), keyboard()
    if command in {"/contract", "/contracts"}:
        return build_contract_launch(dashboard), keyboard()
    if command == "/section":
        section = parts[1] if len(parts) > 1 else "entryWindow"
        return build_section(dashboard, section), keyboard()
    if command == "/risk":
        return build_risk(dashboard), keyboard()
    if command == "/alpha":
        return build_alpha(), keyboard()
    if command == "/search":
        if len(parts) < 2:
            return "用法：/search APT", keyboard()
        return build_ticker_report(fetch_ticker(normalize_ticker(parts[1]))), keyboard()
    if command == "/watch":
        return handle_watch(parts, dashboard, state), keyboard()
    if command in {"/ask", "/codex", "/codel"}:
        question = text[len(parts[0]) :].strip()
        if not question:
            return "用法：/ask 现在最值得观察的三个币是什么？", keyboard()
        return ai_answer(question, dashboard, report), keyboard()
    return "未识别指令。\n\n" + help_text(), keyboard()


def handle_watch(parts: list[str], dashboard: dict[str, Any], state: WukongState) -> str:
    action = parts[1].lower() if len(parts) > 1 else "list"
    if action == "list":
        return build_watchlist(dashboard, state)
    if len(parts) < 3:
        return "用法：/watch add APT 或 /watch remove APT"
    ticker = normalize_ticker(parts[2])
    if action == "add":
        if ticker not in state.watchlist:
            state.watchlist.insert(0, ticker)
            state.watchlist = state.watchlist[:80]
            state.save()
        return f"已关注 {ticker}\n\n" + build_watchlist(dashboard, state)
    if action in {"remove", "del", "delete"}:
        state.watchlist = [item for item in state.watchlist if item != ticker]
        state.save()
        return f"已移除 {ticker}\n\n" + build_watchlist(dashboard, state)
    return "用法：/watch add APT 或 /watch remove APT"


def run_once(client: TelegramClient) -> None:
    dashboard = fetch_dashboard()
    report = fetch_report()
    calendar = fetch_calendar()
    summary = build_summary(dashboard, report, calendar)
    write_snapshot(dashboard=dashboard, report=report, calendar=calendar, summary=summary, mode="once")
    results = client.send(summary, reply_markup=keyboard())
    write_telegram_status(
        dashboard=dashboard,
        status="sent",
        mode="once",
        chat_id=client.chat_id,
        sent_types=["summary"],
        message_chunks=len(results),
    )


def run_polling(client: TelegramClient, *, push_interval: int) -> None:
    state = WukongState.load()
    if not client.chat_id and state.chat_id:
        client.chat_id = state.chat_id
    me = client.get_me().get("result", {})
    startup_text = f"悟空 Telegram 控制台已启动：@{me.get('username', 'bot')}\n每 {push_interval} 秒推送一次实时摘要。"
    if client.chat_id:
        client.send(startup_text, reply_markup=keyboard())
    else:
        print(f"{startup_text}\n等待你向机器人发送 /start 以自动绑定 chat_id。", file=sys.stderr)
    next_push_at = 0.0

    while True:
        now = time.time()
        if client.chat_id and now >= next_push_at:
            try:
                dashboard = fetch_dashboard()
                report = fetch_report()
                calendar = fetch_calendar()
                summary = build_summary(dashboard, report, calendar)
                signature = json.dumps(
                    {
                        "generatedAt": dashboard.get("generatedAt"),
                        "entry": [item.get("ticker") for item in (dashboard.get("entryWindow") or [])[:5]],
                        "opp": [item.get("ticker") for item in (dashboard.get("opportunities") or [])[:5]],
                    },
                    ensure_ascii=False,
                )
                if signature != state.last_summary_signature:
                    results = client.send(summary, reply_markup=keyboard())
                    write_telegram_status(
                        dashboard=dashboard,
                        status="sent",
                        mode="polling",
                        chat_id=client.chat_id,
                        sent_types=["summary"],
                        message_chunks=len(results),
                    )
                    state.last_summary_signature = signature
                    state.save()
                else:
                    write_telegram_status(
                        dashboard=dashboard,
                        status="idle",
                        mode="polling",
                        chat_id=client.chat_id,
                    )
            except Exception as exc:
                client.send(f"悟空自动推送失败：{exc}")
                write_telegram_status(
                    dashboard=None,
                    status="error",
                    mode="polling",
                    chat_id=client.chat_id,
                    error=str(exc),
                )
            next_push_at = time.time() + push_interval

        try:
            updates = client.get_updates(state.offset, timeout=20)
            for update in updates:
                state.offset = max(state.offset, int(update["update_id"]) + 1)
                state.save()
                process_update(client, update, state)
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            print(f"polling error: {exc}", file=sys.stderr)
            time.sleep(5)


def run_push_only(client: TelegramClient, *, push_interval: int) -> None:
    if not client.chat_id:
        raise SystemExit("Missing TELEGRAM_CHAT_ID and no Hermes Telegram channel was discovered.")
    state = WukongState.load()
    write_bridge_context(push_interval)
    client.send(f"悟空已接入现有 Telegram 机器人。\n模式：只推送，不抢占 Hermes/Codex 操作入口。\n频率：每 {push_interval} 秒。", reply_markup=keyboard())
    while True:
        try:
            sync_wukong_files()
            dashboard = fetch_dashboard()
            report = fetch_report()
            calendar = fetch_calendar()
            summary = build_summary(dashboard, report, calendar)
            write_snapshot(dashboard=dashboard, report=report, calendar=calendar, summary=summary, mode="push-only")
            sent_types: list[str] = []
            message_chunks = 0
            signature = json.dumps(
                {
                    "generatedAt": dashboard.get("generatedAt"),
                    "entry": [item.get("ticker") for item in (dashboard.get("entryWindow") or [])[:5]],
                    "opp": [item.get("ticker") for item in (dashboard.get("opportunities") or [])[:5]],
                },
                ensure_ascii=False,
            )
            if signature != state.last_summary_signature:
                results = client.send(summary, reply_markup=keyboard())
                message_chunks += len(results)
                sent_types.append("summary")
                state.last_summary_signature = signature
                state.save()
            signal_sig = signal_signature(dashboard)
            if signal_sig != state.last_signal_signature:
                added = auto_watch_signal_tokens(dashboard, state)
                results = client.send(build_signal_alert_with_watch(dashboard, added), reply_markup=ticker_keyboard(dashboard))
                message_chunks += len(results)
                sent_types.append("signal")
                state.last_signal_signature = signal_sig
                state.save()
            priority_sig = priority_signature(dashboard)
            if priority_sig != state.last_priority_signature:
                results = client.send(build_priority_change_alert(dashboard), reply_markup=ticker_keyboard(dashboard))
                message_chunks += len(results)
                sent_types.append("priority")
                state.last_priority_signature = priority_sig
                state.save()
            write_telegram_status(
                dashboard=dashboard,
                status="sent" if sent_types else "idle",
                mode="push-only",
                chat_id=client.chat_id,
                sent_types=sent_types,
                message_chunks=message_chunks,
            )
        except KeyboardInterrupt:
            raise
        except Exception as exc:
            try:
                client.send(f"悟空推送失败：{exc}")
            except Exception:
                print(f"push error: {exc}", file=sys.stderr)
            write_telegram_status(
                dashboard=None,
                status="error",
                mode="push-only",
                chat_id=client.chat_id,
                error=str(exc),
            )
        time.sleep(push_interval)


def process_update(client: TelegramClient, update: dict[str, Any], state: WukongState) -> None:
    callback = update.get("callback_query")
    if callback:
        client.answer_callback(str(callback["id"]))
        text = str(callback.get("data") or "/help")
        chat_id = str((callback.get("message") or {}).get("chat", {}).get("id") or client.chat_id)
    else:
        message = update.get("message") or {}
        text = str(message.get("text") or "").strip()
        chat_id = str((message.get("chat") or {}).get("id") or client.chat_id)

    if not text:
        return
    if chat_id and not client.chat_id:
        client.chat_id = chat_id
        state.chat_id = chat_id
        state.save()
        client.send("悟空已绑定这个 Telegram 对话。之后会每分钟推送实时摘要。", reply_markup=keyboard(), chat_id=chat_id)
    reply, reply_markup = handle_command(text, state)
    client.send(reply, reply_markup=reply_markup, chat_id=chat_id)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Wukong Telegram bot.")
    parser.add_argument("--once", action="store_true", help="Send one summary and exit.")
    parser.add_argument("--push-only", action="store_true", help="Only send scheduled pushes; do not call getUpdates.")
    parser.add_argument("--interval", type=int, default=int(os.getenv("WUKONG_PUSH_INTERVAL_SECONDS", "30")))
    return parser.parse_args()


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def discover_hermes_telegram_chat_id() -> str:
    if not HERMES_CHANNEL_DIRECTORY.exists():
        return ""
    try:
        payload = json.loads(HERMES_CHANNEL_DIRECTORY.read_text(encoding="utf-8"))
        channels = (((payload or {}).get("platforms") or {}).get("telegram") or [])
        for channel in channels:
            chat_id = str(channel.get("id") or "").strip()
            if chat_id:
                return chat_id
    except Exception:
        return ""
    return ""


def main() -> int:
    args = parse_args()
    load_env_file(Path("/Users/wangbo/.hermes/.env"))
    load_env_file(Path(".env.telegram"))
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip() or discover_hermes_telegram_chat_id()
    if not token:
        print("Missing TELEGRAM_BOT_TOKEN. Put it in /Users/wangbo/.hermes/.env or .env.telegram.", file=sys.stderr)
        return 2
    client = TelegramClient(token, chat_id)
    if args.once:
        run_once(client)
        return 0
    if args.push_only:
        run_push_only(client, push_interval=max(30, args.interval))
        return 0
    run_polling(client, push_interval=max(30, args.interval))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
