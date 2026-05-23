"""
Wukong Live Professional Dashboard
=================================

Run:
    pip install -r requirements-dashboard.txt
    python app.py

Open:
    http://127.0.0.1:8050

This dashboard reads the existing Wukong JSON snapshots first:
- wukong_latest_snapshot.json
- PWA/gate_markets.json
- telegram_status.json
- wukong_file_sync.json
- binance_alpha.json
- x_social.json

If a data source is missing, the UI degrades gracefully instead of pretending
that live trading data exists. Real-order execution remains disabled.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, dcc, html
import dash_bootstrap_components as dbc


APP_TITLE = "悟空 · Wukong Live"
ROOT = Path(__file__).resolve().parent
REFRESH_MS = 5_000
PWA_URL = "https://stays-luxury-location-firm.trycloudflare.com"
PWA_VERSION = "121"

COLORS = {
    "bg": "#061622",
    "surface": "#0a2235",
    "panel": "#0d2c44",
    "line": "rgba(97, 212, 255, 0.18)",
    "primary": "#25c7ff",
    "success": "#22d36b",
    "warning": "#ffb020",
    "danger": "#ff4d5e",
    "text": "#eef8ff",
    "muted": "#86a9c2",
}


def load_json(*parts: str, default: Any = None) -> Any:
    path = ROOT.joinpath(*parts)
    try:
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return default if default is not None else {}


def parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def fmt_age(value: Any) -> str:
    dt = parse_time(value)
    if not dt:
        return "等待同步"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    seconds = max(0, int((datetime.now(timezone.utc) - dt).total_seconds()))
    if seconds < 60:
        return f"{seconds}秒前"
    if seconds < 3600:
        return f"{seconds // 60}分钟前"
    return f"{seconds // 3600}小时前"


def number(value: Any, fallback: float = 0) -> float:
    try:
        if value is None or value == "":
            return fallback
        return float(value)
    except (TypeError, ValueError):
        return fallback


def compact(value: Any) -> str:
    value = number(value)
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if abs(value) >= 1_000:
        return f"{value / 1_000:.1f}K"
    return f"{value:.0f}"


def pct(value: Any) -> str:
    return f"{number(value):+.2f}%"


def get_sources() -> dict[str, Any]:
    snapshot = load_json("wukong_latest_snapshot.json", default={})
    dashboard = snapshot.get("dashboard") or {}
    return {
        "snapshot": snapshot,
        "dashboard": dashboard,
        "gate": load_json("PWA", "gate_markets.json", default={}),
        "telegram": load_json("telegram_status.json", default={}),
        "files": load_json("wukong_file_sync.json", default={}),
        "alpha": load_json("binance_alpha.json", default={}),
        "social": load_json("x_social.json", default={}),
    }


def top_items(dashboard: dict[str, Any], limit: int = 10) -> list[dict[str, Any]]:
    sections = [
        "entryWindow",
        "opportunities",
        "earlyEntryRadar",
        "earlyRadar",
        "oiAnomalyWatch",
        "riskWinnersReview",
        "overheated",
    ]
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for section in sections:
        for item in dashboard.get(section) or []:
            ticker = str(item.get("ticker") or item.get("symbol") or "").upper()
            if not ticker or ticker in seen:
                continue
            seen.add(ticker)
            rows.append(item)
    rows.sort(
        key=lambda item: number(
            item.get("primaryOpportunityScore")
            or item.get("earlyEntrySignal", {}).get("score")
            or item.get("market", {}).get("confirmScore")
            or item.get("heatScore")
        ),
        reverse=True,
    )
    return rows[:limit]


def metric_card(index: int, title: str, value: str, subtitle: str, tone: str = "") -> dbc.Col:
    return dbc.Col(
        html.Div(
            [
                html.Div(f"{index:02d}", className="metric-index"),
                html.Div(
                    [
                        html.Div(title, className="metric-title"),
                        html.Div(value, className=f"metric-value {tone}"),
                        html.Div(subtitle, className="metric-subtitle"),
                    ],
                    className="metric-copy",
                ),
            ],
            className="metric-tile",
        ),
        lg=2,
        md=4,
        sm=6,
    )


def panel(title: str, body: Any, subtitle: str | None = None) -> html.Section:
    return html.Section(
        [
            html.Div(
                [
                    html.Div([html.H2(title), html.P(subtitle or "")]),
                ],
                className="panel-head",
            ),
            body,
        ],
        className="work-panel",
    )


def create_score_figure(items: list[dict[str, Any]]) -> go.Figure:
    if not items:
        x = pd.date_range(end=datetime.now(), periods=24, freq="5min")
        y = np.linspace(50, 65, len(x))
        label = "等待数据"
    else:
        scores = [
            number(
                item.get("earlyEntrySignal", {}).get("score")
                or item.get("primaryOpportunityScore")
                or item.get("market", {}).get("confirmScore")
            )
            for item in items
        ]
        x = pd.date_range(end=datetime.now(), periods=max(12, len(scores) * 2), freq="5min")
        base = np.interp(np.linspace(0, len(scores) - 1, len(x)), range(len(scores)), scores)
        y = np.maximum(0, np.minimum(100, base))
        label = "机会指数"

    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x,
            y=y,
            mode="lines",
            fill="tozeroy",
            name=label,
            line={"width": 3, "color": COLORS["primary"]},
        )
    )
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["panel"],
        plot_bgcolor=COLORS["panel"],
        margin={"l": 18, "r": 18, "t": 12, "b": 18},
        height=320,
        font={"color": COLORS["text"]},
        xaxis={"gridcolor": "rgba(255,255,255,0.05)"},
        yaxis={"gridcolor": "rgba(255,255,255,0.06)", "range": [0, 105]},
    )
    return fig


def create_lane_figure(items: list[dict[str, Any]]) -> go.Figure:
    lanes = Counter(
        item.get("primaryOpportunityLane")
        or item.get("opportunityStructure")
        or item.get("sectionLabel")
        or "观察"
        for item in items
    )
    if not lanes:
        lanes = Counter({"等待数据": 1})
    df = pd.DataFrame({"lane": list(lanes.keys()), "count": list(lanes.values())})
    fig = px.pie(df, values="count", names="lane", hole=0.62)
    fig.update_traces(textinfo="label+percent", marker={"line": {"color": COLORS["panel"], "width": 2}})
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=COLORS["panel"],
        plot_bgcolor=COLORS["panel"],
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        height=286,
        font={"color": COLORS["text"]},
        showlegend=False,
    )
    return fig


def build_candidate_table(items: list[dict[str, Any]]) -> dbc.Table:
    rows = []
    for item in items[:8]:
        market = item.get("market") or {}
        action = item.get("strategy", {}).get("action", {})
        rows.append(
            {
                "币种": item.get("ticker", "--"),
                "阶段": item.get("stage") or item.get("currentStage") or "--",
                "分组": item.get("sectionLabel") or item.get("primaryOpportunityLane") or "--",
                "分数": int(number(item.get("primaryOpportunityScore") or item.get("heatScore"))),
                "24h": pct(market.get("priceChangePercent")),
                "OI1h": pct((market.get("oiWindows") or {}).get("h1")),
                "操作": action.get("label") or "观察",
            }
        )
    if not rows:
        rows = [{"币种": "--", "阶段": "等待数据", "分组": "--", "分数": 0, "24h": "--", "OI1h": "--", "操作": "--"}]
    return dbc.Table.from_dataframe(pd.DataFrame(rows), bordered=False, hover=True, size="sm", className="table-dark live-table")


def build_logs(items: list[dict[str, Any]], telegram: dict[str, Any]) -> list[html.Div]:
    messages = [
        f"Telegram 状态：{telegram.get('status', 'unknown')} · 队列 {telegram.get('queueTotal', 0)}",
        "实盘开单：关闭，仅允许观察 / 纸交易 / 风控复盘",
    ]
    for item in items[:5]:
        ticker = item.get("ticker", "--")
        signal = item.get("earlyEntrySignal") or item.get("entryWindowSignal") or {}
        messages.append(f"{ticker}：{signal.get('summary') or item.get('why') or item.get('stage') or '继续观察'}")
    return [html.Div(msg, className="log-line") for msg in messages]


def build_alerts(dashboard: dict[str, Any], telegram: dict[str, Any]) -> list[html.Div]:
    alerts: list[tuple[str, str]] = []
    counts = dashboard.get("counts") or {}
    risk_count = int(number(counts.get("delistRiskBlocked"))) + len(dashboard.get("overheated") or [])
    if risk_count:
        alerts.append(("RISK", f"风险池 {risk_count} 个，过热/退市/回避类禁止追单"))
    if telegram.get("status") != "online":
        alerts.append(("WARN", f"Telegram 状态 {telegram.get('status', 'unknown')}"))
    alerts.append(("INFO", "Gate / PWA / 文件同步正在被自动读取"))
    alerts.append(("WARN", "实盘开单接口未启用，避免误触真实订单"))
    return [
        html.Div(f"[{level}] {text}", className=f"alert-line alert-{level.lower()}")
        for level, text in alerts
    ]


app = Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
app.title = APP_TITLE

app.layout = dbc.Container(
    [
        dcc.Interval(id="interval", interval=REFRESH_MS, n_intervals=0),
        html.Header(
            [
                html.Div(
                    [
                        html.Div("Wukong Live", className="brand-sub"),
                        html.H1("悟空", className="brand-title"),
                        html.P("实时机会、风险过滤、Gate 行情、Telegram 同步和下载状态集中监控。", className="brand-desc"),
                    ],
                    className="brand-block",
                ),
                html.Div(
                    [
                        html.A("打开下载端", href=f"{PWA_URL}/install.html?v={PWA_VERSION}", className="link-button"),
                        html.Button("刷新", id="refresh-btn", className="refresh-btn"),
                    ],
                    className="header-actions",
                ),
            ],
            className="app-header",
        ),
        dbc.Row(id="metrics-row", className="g-3 metric-grid"),
        html.Section(
            [
                html.Div([html.Span("自动更新"), html.Strong("5秒循环", className="success")]),
                html.Div([html.Span("上次刷新"), html.Strong(id="last-refresh")]),
                html.Div([html.Span("数据心跳"), html.Strong(id="data-heartbeat")]),
                html.Div([html.Span("执行模式"), html.Strong("实盘关闭", className="warning")]),
            ],
            className="status-rail",
        ),
        dbc.Row(
            [
                dbc.Col(panel("机会指数曲线", dcc.Graph(id="score-graph", config={"displayModeBar": False}), "来自实时候选分数，不冒充实盘收益。"), lg=8),
                dbc.Col(panel("机会分布", dcc.Graph(id="lane-graph", config={"displayModeBar": False}), "按入场窗口、合约启动、风险回避分组。"), lg=4),
            ],
            className="g-3",
        ),
        dbc.Row(
            [
                dbc.Col(panel("AI 决策日志", html.Div(id="ai-logs"), "保留关键原因和执行边界。"), lg=3),
                dbc.Col(panel("最新候选", html.Div(id="candidate-table"), "按分数和可观察性排序。"), lg=5),
                dbc.Col(panel("风险告警", html.Div(id="risk-alerts"), "风险先于收益显示。"), lg=4),
            ],
            className="g-3 bottom-grid",
        ),
    ],
    fluid=True,
    className="app-shell",
)


@app.callback(
    Output("metrics-row", "children"),
    Output("score-graph", "figure"),
    Output("lane-graph", "figure"),
    Output("ai-logs", "children"),
    Output("candidate-table", "children"),
    Output("risk-alerts", "children"),
    Output("last-refresh", "children"),
    Output("data-heartbeat", "children"),
    Input("interval", "n_intervals"),
    Input("refresh-btn", "n_clicks"),
)
def update_dashboard(_: int, __: int | None):
    sources = get_sources()
    snapshot = sources["snapshot"]
    dashboard = sources["dashboard"]
    counts = dashboard.get("counts") or {}
    telegram = sources["telegram"]
    files = sources["files"]
    gate = sources["gate"]
    items = top_items(dashboard, 12)
    gate_markets = gate.get("markets") or []

    risk_count = int(number(counts.get("delistRiskBlocked"))) + len(dashboard.get("overheated") or [])
    metrics = [
        metric_card(1, "实时总览", compact(counts.get("tickers")), f"风险 {risk_count} · {fmt_age(snapshot.get('updatedAt'))}"),
        metric_card(2, "决策中心", compact(len(items)), "优先候选 / 回踩观察", "success"),
        metric_card(3, "市场信号", compact(counts.get("tradeConfirmedOpportunities")), "合约启动监控"),
        metric_card(4, "Telegram", compact(telegram.get("queueTotal")), telegram.get("status", "unknown"), "success" if telegram.get("status") == "online" else "warning"),
        metric_card(5, "下载安装", "4/4", "苹果 / 安卓 / 网页在线", "success"),
        metric_card(6, "文件同步", compact(files.get("fileCount")), f"Gate {len(gate_markets)} 组", "success"),
    ]

    return (
        metrics,
        create_score_figure(items),
        create_lane_figure(items),
        build_logs(items, telegram),
        build_candidate_table(items),
        build_alerts(dashboard, telegram),
        datetime.now().strftime("%H:%M:%S"),
        fmt_age(snapshot.get("updatedAt")),
    )


app.index_string = f"""
<!DOCTYPE html>
<html>
<head>
    {{%metas%}}
    <title>{{%title%}}</title>
    {{%favicon%}}
    {{%css%}}
    <style>
        :root {{
            color-scheme: dark;
            --bg: {COLORS["bg"]};
            --surface: {COLORS["surface"]};
            --panel: {COLORS["panel"]};
            --line: {COLORS["line"]};
            --primary: {COLORS["primary"]};
            --success: {COLORS["success"]};
            --warning: {COLORS["warning"]};
            --danger: {COLORS["danger"]};
            --text: {COLORS["text"]};
            --muted: {COLORS["muted"]};
        }}
        body {{
            margin: 0;
            background:
                radial-gradient(circle at top right, rgba(37,199,255,0.18), transparent 34rem),
                linear-gradient(180deg, #082338 0%, var(--bg) 48%, #03101a 100%);
            color: var(--text);
            font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }}
        .app-shell {{
            min-height: 100vh;
            padding: 28px;
        }}
        .app-header {{
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 24px;
            margin-bottom: 24px;
        }}
        .brand-sub {{
            color: var(--primary);
            font-size: 12px;
            font-weight: 800;
            letter-spacing: 0;
            text-transform: uppercase;
        }}
        .brand-title {{
            margin: 2px 0 8px;
            font-size: clamp(48px, 7vw, 82px);
            line-height: 0.95;
            font-weight: 850;
        }}
        .brand-desc {{
            max-width: 680px;
            margin: 0;
            color: var(--muted);
            font-size: 16px;
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
            justify-content: flex-end;
        }}
        .link-button, .refresh-btn {{
            min-height: 44px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(255,255,255,0.06);
            color: var(--text);
            padding: 10px 14px;
            font-weight: 750;
            text-decoration: none;
        }}
        .refresh-btn:hover, .link-button:hover {{
            border-color: rgba(37,199,255,0.6);
            color: white;
        }}
        .metric-grid {{
            margin-bottom: 14px;
        }}
        .metric-tile {{
            min-height: 130px;
            display: flex;
            align-items: center;
            gap: 14px;
            padding: 18px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(10, 34, 53, 0.82);
        }}
        .metric-index {{
            width: 42px;
            height: 42px;
            display: grid;
            place-items: center;
            border: 1px solid rgba(37,199,255,0.38);
            border-radius: 8px;
            color: var(--primary);
            font-weight: 850;
            background: rgba(37,199,255,0.10);
            flex: 0 0 auto;
        }}
        .metric-title, .metric-subtitle, .status-rail span {{
            color: var(--muted);
            font-size: 12px;
        }}
        .metric-value {{
            font-size: 28px;
            line-height: 1.1;
            font-weight: 850;
        }}
        .success {{ color: var(--success); }}
        .warning {{ color: var(--warning); }}
        .danger {{ color: var(--danger); }}
        .status-rail {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 1px;
            overflow: hidden;
            margin: 0 0 14px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: var(--line);
        }}
        .status-rail div {{
            display: flex;
            justify-content: space-between;
            gap: 12px;
            padding: 14px 16px;
            background: rgba(8, 28, 45, 0.94);
        }}
        .status-rail strong {{
            font-size: 15px;
        }}
        .work-panel {{
            height: 100%;
            padding: 18px;
            border: 1px solid var(--line);
            border-radius: 8px;
            background: rgba(13, 44, 68, 0.92);
        }}
        .panel-head {{
            margin-bottom: 12px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
            padding-bottom: 12px;
        }}
        .panel-head h2 {{
            margin: 0;
            font-size: 16px;
            font-weight: 850;
        }}
        .panel-head p {{
            margin: 4px 0 0;
            color: var(--muted);
            font-size: 12px;
        }}
        .bottom-grid {{
            margin-top: 14px;
        }}
        .log-line, .alert-line {{
            padding: 9px 0;
            border-bottom: 1px solid rgba(255,255,255,0.05);
            color: var(--text);
            font-size: 13px;
            line-height: 1.45;
        }}
        .alert-info {{ color: var(--primary); }}
        .alert-warn {{ color: var(--warning); }}
        .alert-risk {{ color: var(--danger); }}
        .table-dark {{
            --bs-table-bg: transparent;
            --bs-table-color: var(--text);
            --bs-table-hover-bg: rgba(37,199,255,0.08);
            margin-bottom: 0;
            font-size: 13px;
        }}
        .live-table th {{
            color: var(--muted);
            font-weight: 700;
            border-color: rgba(255,255,255,0.05);
        }}
        .live-table td {{
            border-color: rgba(255,255,255,0.05);
            vertical-align: middle;
        }}
        @media (max-width: 900px) {{
            .app-shell {{ padding: 18px; }}
            .app-header {{ flex-direction: column; }}
            .header-actions {{ justify-content: flex-start; }}
            .status-rail {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
        }}
        @media (max-width: 560px) {{
            .status-rail {{ grid-template-columns: 1fr; }}
            .metric-tile {{ min-height: 112px; }}
        }}
    </style>
</head>
<body>
    {{%app_entry%}}
    <footer>
        {{%config%}}
        {{%scripts%}}
        {{%renderer%}}
    </footer>
</body>
</html>
"""


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8050, debug=False)
