const API_BASE = "https://michill.ai";
const GATE_BASE = "https://api.gateio.ws/api/v4";
const SNAPSHOT_URL = "./wukong_latest_snapshot.json";
const EXCHANGE_SNAPSHOT_URL = "./exchange_markets.json";
const GATE_PRIVATE_STATUS_URL = "./gate_private_status.json";
const GATE_TRADE_PREFLIGHT_URL = "./gate_trade_preflight.json";
const PAPER_TRADING_STATE_URL = "./paper_trading_state.json";
const PROFESSIONAL_SYSTEM_URL = "./professional_trade_system.json";
const EMA_CROSS_4H_URL = "./ema_cross_4h.json";
const GATE_SNAPSHOT_URL = "./gate_markets.json";
const X_SOCIAL_URL = "./x_social.json";
const ALPHA_URL = "./binance_alpha.json";
const TELEGRAM_STATUS_URL = "./telegram_status.json";
const REFRESH_MS = 30_000;
const GATE_PAIRS = ["BTC_USDT", "ETH_USDT", "SOL_USDT", "BNB_USDT"];
const WATCHLIST_KEY = "wukong.watchlist.v1";
const APP_VERSION = "122";
const LOCAL_FILE_MODE = window.location.protocol === "file:";
const REMOTE_BROWSER_FETCH = false;
const DOWNLOAD_CHECKS = [
  { label: "iPhone安装", kind: "配置文件", url: `./downloads/wukong-ios-install.mobileconfig?v=${APP_VERSION}` },
  { label: "Android APK", kind: "安装包", url: `./downloads/wukong-android-release.apk?v=${APP_VERSION}` },
  { label: "苹果二维码", kind: "二维码", url: `./qr/wukong-ios-qr.png?v=${APP_VERSION}` },
  { label: "安卓二维码", kind: "二维码", url: `./qr/wukong-android-qr.png?v=${APP_VERSION}` },
];
const EXCHANGE_CONNECTORS = [
  { id: "binance", name: "Binance", scope: "现货 / USDT 合约 / 资金费率", status: "public" },
  { id: "okx", name: "OKX", scope: "现货 / SWAP / 资金费率", status: "public" },
  { id: "gate", name: "Gate", scope: "现货 + USDT 合约", status: "live" },
];
const GATE_EXIT_RULE = {
  takeProfits: [
    { pct: 3.5, close: 25 },
    { pct: 7.5, close: 25 },
    { pct: 12, close: 50 },
  ],
  baseStopPct: 2.4,
  maxStopPct: 5.5,
};

const sectionLabels = {
  entryWindow: "入场窗口",
  earlyEntryRadar: "早发现雷达",
  opportunities: "确认/回踩候选",
  risk: "风险区",
  oiAnomalyWatch: "OI异动",
  repeatCandidateWatch: "多次出现",
  recentSignalChanges: "信号轨迹",
  delistRiskWatch: "公告风险",
  overheated: "过热回避",
};

const stageWeights = {
  "小仓试错": 30,
  "重点候选": 26,
  "等待回踩": 18,
  "观察": 8,
};

const state = {
  dashboard: null,
  snapshotMeta: null,
  dataMode: "连接中",
  watchlist: loadWatchlist(),
  briefRows: [],
  report: null,
  calendar: null,
  section: "entryWindow",
  timer: null,
  countdownTimer: null,
  nextRefreshAt: 0,
  lastRefreshAt: 0,
  deferredPrompt: null,
  fileSync: null,
  exchangeMarkets: null,
  exchangeSnapshotTime: null,
  gatePrivate: null,
  gatePreflight: null,
  paperTrading: null,
  professionalSystem: null,
  emaCross4h: null,
  gateMarkets: [],
  gateSnapshotTime: null,
  xSocial: null,
  alpha: null,
  telegramStatus: null,
  downloadHealth: [],
  refreshInFlight: false,
  lastRefreshError: "",
};

const $ = (selector) => document.querySelector(selector);
const setText = (selector, value) => {
  const element = $(selector);
  if (element) element.textContent = value;
};
const setWidth = (selector, value) => {
  const element = $(selector);
  if (element) element.style.width = value;
};
const setHTML = (selector, value) => {
  const element = $(selector);
  if (element) element.innerHTML = value;
};

function loadWatchlist() {
  try {
    const rows = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]");
    if (Array.isArray(rows)) return rows.map((item) => String(item).toUpperCase()).filter(Boolean).slice(0, 40);
  } catch {
    return [];
  }
  return [];
}

function saveWatchlist() {
  try {
    localStorage.setItem(WATCHLIST_KEY, JSON.stringify(state.watchlist));
  } catch {
    // 本地存储不可用时，关注只在当前页面会话内生效。
  }
}

function isWatched(ticker) {
  return state.watchlist.includes(String(ticker || "").toUpperCase());
}

function toggleWatch(ticker) {
  const value = String(ticker || "").toUpperCase().trim();
  if (!value) return;
  if (isWatched(value)) {
    state.watchlist = state.watchlist.filter((item) => item !== value);
  } else {
    state.watchlist = [value, ...state.watchlist.filter((item) => item !== value)].slice(0, 40);
  }
  saveWatchlist();
  renderPriority();
  renderSearchResults();
  renderWatchlist();
}

function fmtTime(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value).slice(0, 16);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function fmtPct(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${number >= 0 ? "+" : ""}${number.toFixed(1)}%`;
}

function fmtPrice(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  if (number >= 1000) return number.toLocaleString("en-US", { maximumFractionDigits: 1 });
  if (number >= 1) return number.toLocaleString("en-US", { maximumFractionDigits: 4 });
  return number.toLocaleString("en-US", { maximumFractionDigits: 8 });
}

function fmtFunding(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "--";
  return `${(number * 100).toFixed(4)}%`;
}

function fmtSignedPct(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) return "--";
  return `${parsed >= 0 ? "+" : ""}${parsed.toFixed(1)}%`;
}

function fmtAge(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  const seconds = Math.max(0, Math.round((Date.now() - date.getTime()) / 1000));
  if (seconds < 60) return `${seconds}秒前`;
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}分钟前`;
  const hours = Math.round(minutes / 60);
  return `${hours}小时前`;
}

function scoreClass(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  return number >= 0 ? "positive" : "negative";
}

function number(value, fallback = 0) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : fallback;
}

function safeText(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

const SAFE_DYNAMIC_PROTOCOLS = new Set(["http:", "https:", "mailto:", "tel:", "tg:"]);
const BLOCKED_DYNAMIC_TAGS = new Set(["SCRIPT", "IFRAME", "OBJECT", "EMBED"]);

function sanitizeDynamicMarkup(root = document.body) {
  if (!root || !root.querySelectorAll) return;
  const nodes = root.nodeType === Node.ELEMENT_NODE ? [root, ...root.querySelectorAll("*")] : [...root.querySelectorAll("*")];
  for (const node of nodes) {
    if (BLOCKED_DYNAMIC_TAGS.has(node.tagName)) {
      node.remove();
      continue;
    }
    for (const attribute of [...node.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on")) {
        node.removeAttribute(attribute.name);
        continue;
      }
      if ((name === "href" || name === "src") && value) {
        try {
          const parsed = new URL(value, window.location.href);
          if (!SAFE_DYNAMIC_PROTOCOLS.has(parsed.protocol)) node.removeAttribute(attribute.name);
        } catch {
          node.removeAttribute(attribute.name);
        }
      }
    }
    if (node.tagName === "A" && node.getAttribute("target") === "_blank") {
      const rel = new Set(String(node.getAttribute("rel") || "").toLowerCase().split(/\s+/).filter(Boolean));
      rel.add("noopener");
      rel.add("noreferrer");
      const nextRel = [...rel].join(" ");
      if (node.getAttribute("rel") !== nextRel) node.setAttribute("rel", nextRel);
    }
  }
}

function startDynamicMarkupGuard() {
  const descriptor = Object.getOwnPropertyDescriptor(Element.prototype, "innerHTML");
  if (descriptor?.set && descriptor?.get && !Element.prototype.__wukongInnerHTMLGuarded) {
    Object.defineProperty(Element.prototype, "innerHTML", {
      configurable: true,
      enumerable: descriptor.enumerable,
      get() {
        return descriptor.get.call(this);
      },
      set(value) {
        descriptor.set.call(this, value);
        if (this.isConnected && this !== document.documentElement) sanitizeDynamicMarkup(this);
      },
    });
    Object.defineProperty(Element.prototype, "__wukongInnerHTMLGuarded", { value: true });
  }
  sanitizeDynamicMarkup();
  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === "attributes") {
        sanitizeDynamicMarkup(mutation.target);
      } else {
        mutation.addedNodes.forEach((node) => {
          if (node.nodeType === Node.ELEMENT_NODE) sanitizeDynamicMarkup(node);
        });
      }
    }
  });
  observer.observe(document.body, { subtree: true, childList: true, attributes: true });
}

function tokenMetric(item) {
  const market = item.market || {};
  const signal = item.entryWindowSignal || item.earlyEntrySignal || {};
  const oi = market.oiWindows || item.oi || {};
  const change = market.priceChangePercent ?? item.price24h;
  const score = signal.score ?? item.heatScore ?? "--";
  return {
    ticker: item.ticker || "--",
    stage: item.currentStage || item.stage || "观察",
    structure: item.opportunityStructure || item.primaryOpportunityLane || "信号",
    change,
    oi: oi.h1 ?? oi.h6 ?? "--",
    score,
  };
}

function actionBucket(item) {
  const stage = String(item.currentStage || item.stage || "");
  const structure = String(item.opportunityStructure || item.primaryOpportunityLane || "");
  if (stage.includes("小仓")) return "小仓试错";
  if (stage.includes("重点")) return "重点候选";
  if (stage.includes("回踩") || structure.includes("回踩")) return "等待回踩";
  return stage || "观察";
}

function signalScore(item) {
  const metric = tokenMetric(item);
  const bucket = actionBucket(item);
  return (
    (stageWeights[bucket] || stageWeights["观察"]) +
    number(metric.score) +
    Math.max(-20, Math.min(30, number(metric.oi))) +
    Math.max(-12, Math.min(18, number(metric.change) / 2))
  );
}

function nextAction(item) {
  const bucket = actionBucket(item);
  const metric = tokenMetric(item);
  const oi = number(metric.oi);
  const change = number(metric.change);
  if (bucket === "小仓试错") {
    if (oi > 6 && change > 8) return "只看小仓纸面验证，等 5m/15m 回踩不破再复核。";
    return "观察承接和 OI 是否继续温和增加，不追第一根放量。";
  }
  if (bucket === "重点候选") {
    return "优先盯回踩承接，价格稳住且费率不过热再升级。";
  }
  if (bucket === "等待回踩") {
    return "等待缩量回踩后重新放量，未回踩前不追高。";
  }
  return "只观察，等信号进入入场或确认候选再处理。";
}

function priorityItems() {
  const dashboard = state.dashboard || {};
  const rows = [
    ...(dashboard.entryWindow || []),
    ...(dashboard.earlyEntryRadar || []),
    ...(dashboard.opportunities || []),
  ];
  const byTicker = new Map();
  for (const item of rows) {
    const ticker = String(item.ticker || "").toUpperCase();
    if (!ticker) continue;
    const stage = String(item.currentStage || item.stage || "");
    const structure = String(item.opportunityStructure || item.primaryOpportunityLane || "");
    if (stage.includes("回避") || stage.includes("风险") || structure.includes("回避")) continue;
    const previous = byTicker.get(ticker);
    if (!previous || signalScore(item) > signalScore(previous)) byTicker.set(ticker, item);
  }
  return [...byTicker.values()].sort((a, b) => signalScore(b) - signalScore(a));
}

function contractLaunchItems() {
  const dashboard = state.dashboard || {};
  const alphaRows = (state.alpha?.tokens || []).map((item) => ({
    ticker: item.ticker,
    currentStage: item.stage || "Alpha映射",
    opportunityStructure: item.note || "Binance Alpha 映射候选",
    market: {
      priceChangePercent: item.change24h,
      oiWindows: { h1: item.oi1h },
    },
    entryWindowSignal: { score: item.alphaScore },
  }));
  const rows = [
    ...(dashboard.oiAnomalyWatch || []),
    ...(dashboard.entryWindow || []),
    ...(dashboard.earlyEntryRadar || []),
    ...alphaRows,
  ];
  const byTicker = new Map();
  for (const item of rows) {
    const ticker = String(item.ticker || "").toUpperCase();
    if (!ticker) continue;
    const stage = String(item.currentStage || item.stage || "");
    const structure = String(item.opportunityStructure || item.primaryOpportunityLane || "");
    if (stage.includes("回避") || stage.includes("风险") || structure.includes("退役")) continue;
    const previous = byTicker.get(ticker);
    if (!previous || signalScore(item) > signalScore(previous)) byTicker.set(ticker, item);
  }
  return [...byTicker.values()].sort((a, b) => signalScore(b) - signalScore(a)).slice(0, 8);
}

function paperPlanFor(item) {
  if (!item) return null;
  const preflightPlan = state.gatePreflight?.paperTrade?.plan;
  if (preflightPlan) {
    const tiers = (preflightPlan.takeProfitTiers || GATE_EXIT_RULE.takeProfits)
      .map((rule, index) => `第${index + 1}档 +${rule.triggerPct ?? rule.pct}% 平 ${rule.closePct ?? rule.close}%`)
      .join(" · ");
    return {
      ticker: String(preflightPlan.market || "--").replace("_USDT", "").toUpperCase(),
      side: "自动纸交易多单",
      notional: `${preflightPlan.maxNotionalUsdt ?? "--"}U`,
      leverage: `${preflightPlan.leverage ?? "--"}x`,
      stop: `-${preflightPlan.stopLossPct ?? GATE_EXIT_RULE.baseStopPct}%`,
      stopDetail: `基础止损 ${preflightPlan.stopLossPct ?? GATE_EXIT_RULE.baseStopPct}%，最多放宽到 ${preflightPlan.maxStopLossPct ?? GATE_EXIT_RULE.maxStopPct}%`,
      takeProfit: "3档",
      takeProfitPlan: tiers,
      trigger: state.gatePreflight?.paperTrade?.reason || "信号出现自动生成，信号消失自动关闭",
      margin: `${preflightPlan.maxMarginUsdt ?? "--"}U`,
      risk: `${preflightPlan.riskPerTradeUsdt ?? "--"}U`,
    };
  }
  const metric = tokenMetric(item);
  const score = Math.round(signalScore(item));
  const oi = number(metric.oi);
  const change = number(metric.change);
  const riskUnit = score >= 70 && oi > 8 ? 1 : 0.5;
  const leverage = score >= 78 ? 3 : 2;
  const takeProfitPlan = GATE_EXIT_RULE.takeProfits
    .map((rule, index) => `第${index + 1}档 +${rule.pct}% 平 ${rule.close}%`)
    .join(" · ");
  return {
    ticker: String(metric.ticker || "--").toUpperCase(),
    side: change >= -3 ? "观察多单" : "等待确认",
    notional: `${riskUnit}% 账户`,
    leverage: `${leverage}x`,
    stop: `-${GATE_EXIT_RULE.baseStopPct}%`,
    stopDetail: `基础止损 ${GATE_EXIT_RULE.baseStopPct}%，最多放宽到 ${GATE_EXIT_RULE.maxStopPct}%`,
    takeProfit: "3档",
    takeProfitPlan,
    trigger: `${metric.stage} · OI ${fmtPct(metric.oi)} · 分 ${score}`,
  };
}

function searchableItems() {
  const dashboard = state.dashboard || {};
  const sections = [
    "entryWindow",
    "earlyEntryRadar",
    "opportunities",
    "oiAnomalyWatch",
    "repeatCandidateWatch",
    "recentSignalChanges",
    "delistRiskWatch",
    "overheated",
  ];
  const rows = [];
  for (const section of sections) {
    for (const item of dashboard[section] || []) {
      if (!item?.ticker) continue;
      rows.push({ section, item });
    }
  }
  return rows;
}

function bestMatchForTicker(ticker) {
  const value = String(ticker || "").toUpperCase();
  return searchableItems()
    .filter(({ item }) => String(item.ticker || "").toUpperCase() === value)
    .sort((a, b) => signalScore(b.item) - signalScore(a.item))[0];
}

function renderSearchResults() {
  const input = $("#tokenSearch");
  if (!input) return;
  const query = input.value.trim().toUpperCase();
  if (!query) {
    $("#searchResultCount").textContent = "待输入";
    $("#searchResults").innerHTML = '<div class="empty compact">输入币种后显示位置、阶段和关键指标</div>';
    return;
  }
  const rows = searchableItems()
    .filter(({ item }) => String(item.ticker || "").toUpperCase().includes(query))
    .slice(0, 10);
  $("#searchResultCount").textContent = `${rows.length} 条`;
  if (!rows.length) {
    $("#searchResults").innerHTML = '<div class="empty compact">没有找到这个币种</div>';
    return;
  }
  $("#searchResults").innerHTML = rows.map(({ section, item }) => {
    const metric = tokenMetric(item);
    return `
      <article class="search-row">
        <div>
          <strong>${metric.ticker}</strong>
          <span>${sectionLabels[section] || section} · ${metric.stage}</span>
        </div>
        <div>
          <strong class="${scoreClass(metric.change)}">${fmtPct(metric.change)}</strong>
          <span>OI ${fmtPct(metric.oi)} · 分 ${metric.score}</span>
        </div>
        <button class="watch-button ${isWatched(metric.ticker) ? "is-active" : ""}" type="button" data-watch-toggle="${metric.ticker}">
          ${isWatched(metric.ticker) ? "已关注" : "关注"}
        </button>
      </article>
    `;
  }).join("");
}

function renderWatchlist() {
  $("#watchCount").textContent = `${state.watchlist.length} 个`;
  if (!state.watchlist.length) {
    $("#watchList").innerHTML = '<div class="empty compact">还没有关注币种，可从搜索或 Top 5 添加</div>';
    return;
  }
  $("#watchList").innerHTML = state.watchlist.map((ticker) => {
    const match = bestMatchForTicker(ticker);
    if (!match) {
      return `
        <article class="watch-row">
          <div>
            <strong>${ticker}</strong>
            <span>当前快照未出现</span>
          </div>
          <div>
            <strong>等待</strong>
            <span>继续同步</span>
          </div>
          <button class="watch-button is-active" type="button" data-watch-toggle="${ticker}">移除</button>
        </article>
      `;
    }
    const metric = tokenMetric(match.item);
    return `
      <article class="watch-row">
        <div>
          <strong>${metric.ticker}</strong>
          <span>${sectionLabels[match.section] || match.section} · ${metric.stage}</span>
        </div>
        <div>
          <strong class="${scoreClass(metric.change)}">${fmtPct(metric.change)}</strong>
          <span>OI ${fmtPct(metric.oi)} · 分 ${Math.round(signalScore(match.item))}</span>
        </div>
        <button class="watch-button is-active" type="button" data-watch-toggle="${metric.ticker}">移除</button>
      </article>
    `;
  }).join("");
}

function signalTone(item) {
  const text = `${item.statusLabel || ""} ${item.currentStage || ""} ${item.stage || ""}`;
  if (text.includes("退役") || text.includes("回避") || text.includes("风险")) return "danger";
  if (text.includes("升级") || text.includes("入场") || text.includes("小仓")) return "good";
  return "watch";
}

function compactText(value, limit = 96) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  if (!text) return "等待下一轮同步确认。";
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

function renderSignalTrail() {
  const rows = state.dashboard?.recentSignalChanges || [];
  $("#signalTrailCount").textContent = `${rows.length} 条`;
  if (!rows.length) {
    $("#signalTrailList").innerHTML = '<div class="empty compact">当前没有新的信号轨迹</div>';
    return;
  }
  $("#signalTrailList").innerHTML = rows.slice(0, 8).map((item) => `
    <article class="signal-row ${signalTone(item)}">
      <div>
        <strong>${item.ticker || "--"}</strong>
        <span>${item.statusLabel || "变化"} · ${item.currentStage || item.stage || "观察"}</span>
      </div>
      <p>${item.reason || "等待下一轮同步确认。"}</p>
    </article>
  `).join("");
}

function riskRadarItems() {
  const dashboard = state.dashboard || {};
  const rows = [
    ...(dashboard.delistRiskWatch || []).map((item) => ({ source: "公告风险", item })),
    ...(dashboard.overheated || []).map((item) => ({ source: "过热回避", item })),
    ...(dashboard.recentSignalChanges || [])
      .filter((item) => signalTone(item) === "danger")
      .map((item) => ({ source: item.statusLabel || "信号退役", item })),
  ];
  const byTicker = new Map();
  for (const row of rows) {
    const ticker = String(row.item.ticker || "").toUpperCase();
    if (!ticker) continue;
    if (!byTicker.has(ticker)) byTicker.set(ticker, row);
  }
  return [...byTicker.values()];
}

function renderRiskRadar() {
  const rows = riskRadarItems();
  $("#riskRadarCount").textContent = `${rows.length} 个`;
  if (!rows.length) {
    $("#riskRadarList").innerHTML = '<div class="empty compact">当前没有风险雷达项目</div>';
    return;
  }
  $("#riskRadarList").innerHTML = rows.slice(0, 2).map(({ source, item }) => {
    const metric = tokenMetric(item);
    const reason = item.reason || item.why || item.opportunityStructure || "风险过滤中，先观察不追。";
    return `
      <article class="risk-row">
        <div>
          <strong>${metric.ticker}</strong>
          <span>${source} · ${metric.stage}</span>
        </div>
        <div>
          <strong class="${scoreClass(metric.change)}">${fmtPct(metric.change)}</strong>
          <span>分 ${metric.score}</span>
        </div>
        <p>${compactText(reason)}</p>
      </article>
    `;
  }).join("");
}

function renderBrief() {
  const priorities = priorityItems();
  const top = priorities[0] ? tokenMetric(priorities[0]) : null;
  const riskCount = riskRadarItems().length;
  const trailCount = state.dashboard?.recentSignalChanges?.length || 0;
  const watchCount = state.watchlist.length;
  $("#briefStamp").textContent = fmtTime(state.dashboard?.generatedAt);
  const rows = [
    {
      label: "先看",
      value: top ? `${top.ticker} · ${top.stage}` : "暂无优先候选",
      note: top ? `${top.structure} · 24h ${fmtPct(top.change)} · OI ${fmtPct(top.oi)}` : "等待下一轮同步",
    },
    {
      label: "风险",
      value: `${riskCount} 个需回避`,
      note: riskCount ? "先看风险雷达，再看机会列表" : "当前风险雷达为空",
    },
    {
      label: "变化",
      value: `${trailCount} 条轨迹`,
      note: trailCount ? "有升级、退役或转回避变化" : "暂无新的阶段变化",
    },
    {
      label: "关注",
      value: `${watchCount} 个币种`,
      note: watchCount ? "本机关注会随同步刷新" : "可从搜索或 Top 5 添加",
    },
  ];
  state.briefRows = rows;
  $("#briefList").innerHTML = rows.slice(0, 1).map((row) => `
    <article class="brief-row">
      <span>${row.label}</span>
      <div>
        <strong>${row.value}</strong>
        <small>${row.note}</small>
      </div>
    </article>
  `).join("");
}

function renderReview() {
  const calendar = state.calendar || {};
  const report = state.report || {};
  const counts = report.counts || {};
  const publicReport = report.publicReport || {};
  $("#reviewStamp").textContent = fmtTime(calendar.updatedAt || report.generatedAt);
  $("#paperReturn").textContent = fmtSignedPct(calendar.totalReturnPct);
  $("#paperTrades").textContent = calendar.totalTrades ?? "--";
  $("#hit30Count").textContent = counts.hit30 ?? "--";
  $("#reviewReady").textContent = counts.trustedReturns ?? "--";
  $("#reviewStatus").textContent = calendar.totalDays
    ? `${calendar.leverage || 10}x · ${calendar.totalDays} 天 · ${fmtTime(calendar.updatedAt)}`
    : "等待复盘数据。";
  $("#reviewHeadline").textContent =
    publicReport.headline ||
    publicReport.aiPublicHighlights?.[0] ||
    "同步后显示 AI 复盘摘要。";
}

function sourceAgeClass(value) {
  if (!value) return "watch";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "watch";
  const age = Date.now() - date.getTime();
  if (age < 20 * 60_000) return "good";
  if (age < 6 * 60 * 60_000) return "watch";
  return "stale";
}

function renderSources() {
  const sources = state.dashboard?.sources || {};
  const alphaSummary = state.alpha?.summary || {};
  const xSummary = state.xSocial?.summary || {};
  const rows = [
    {
      name: "行情/OI",
      time: sources.marketRadarFetchedAt || state.dashboard?.generatedAt,
      value: `${sources.binanceOiSeedUniverse ?? state.dashboard?.counts?.tickers ?? "--"} OI池 · ${sources.oiConfidenceCoverage?.high ?? 0} 高置信`,
    },
    {
      name: "DEX",
      time: sources.dexScreenerFetchedAt,
      value: `${sources.dexScreenerCandidates ?? "--"} 候选 · ${sources.dexIdentityMappedTickers ?? "--"} 映射`,
    },
    {
      name: "X/推特",
      time: state.xSocial?.updatedAt || sources.xSearchFetchedAt,
      value: `${xSummary.posts ?? sources.xSearchPosts ?? "--"} 帖 · ${xSummary.tickers ?? sources.xSearchTickers ?? "--"} 币`,
    },
    {
      name: "Alpha",
      time: state.alpha?.updatedAt || sources.binanceAlphaCaFetchedAt,
      value: `${alphaSummary.tokens ?? sources.binanceAlphaCaTokens ?? "--"} CA · ${alphaSummary.coveragePct ?? "--"}%`,
    },
    {
      name: "交易所API",
      time: state.exchangeSnapshotTime || state.gateSnapshotTime,
      value: `Binance / OKX / Gate · ${state.exchangeMarkets?.markets?.length || state.gateMarkets?.length || GATE_PAIRS.length} 币`,
    },
  ];
  setText("#sourceStamp", fmtTime(state.dashboard?.generatedAt || state.xSocial?.updatedAt || state.alpha?.updatedAt));
  setHTML("#sourceList", rows.map((row) => `
    <article class="source-row ${sourceAgeClass(row.time)}">
      <div>
        <strong>${row.name}</strong>
        <span>${row.value}</span>
      </div>
      <small>${row.time ? fmtAge(row.time) : "等待同步"}</small>
    </article>
  `).join(""));
}

function renderExchangeCenter() {
  const sources = state.dashboard?.sources || {};
  const liveVenues = Object.values(state.exchangeMarkets?.venues || {}).filter((item) => item.online).length;
  const online = [
    state.dashboard?.generatedAt || sources.marketRadarFetchedAt,
    state.alpha?.updatedAt || state.alpha?.alphaFetchedAt,
    state.exchangeSnapshotTime || state.gateSnapshotTime,
  ].filter(Boolean).length;
  $("#exchangeOnline").textContent = `${Math.max(online, liveVenues)}/3`;
  $("#exchangeMode").textContent = "模拟";
  $("#paperModeState").textContent = "开启";
  const privateStatus = state.gatePrivate;
  setText("#gatePrivateState", privateStatus?.authenticated ? "已验证" : privateStatus?.configured ? "待验证" : "未绑定");
  const liveText = privateStatus?.liveTradingRequested
    ? `已收到实盘申请；${privateStatus.liveTradingBlockedReason || "安全锁未解锁"}。`
    : "";
  $("#exchangeStatus").textContent = privateStatus?.authenticated
    ? `Gate Key 已在后端绑定并验证；当前实盘开单保持关闭。${liveText}`
    : "当前只启用公开行情和纸交易模拟；实盘私有 API 未开启。";
  const riskRows = (privateStatus?.riskControls || []).map((item) => `
    <div class="gate-risk-item ${safeText(item.state || "waiting")}">
      <strong>${safeText(item.name || "--")}</strong>
      <span>${safeText(item.detail || "--")}</span>
    </div>
  `).join("");
  const protectionRows = (privateStatus?.protectionPolicy?.layers || []).map((item, index) => `
    <div class="gate-protection-item ${safeText(item.state || "waiting")}">
      <small>第 ${index + 1} 层</small>
      <strong>${safeText(item.name || "--")}</strong>
      <span>${safeText(item.detail || "--")}</span>
    </div>
  `).join("");
  const readinessRows = (privateStatus?.manualLiveReadiness || []).map((item) => `
    <div class="gate-readiness-item ${item.ok ? "ok" : "blocked"}">
      <strong>${safeText(item.name || "--")}</strong>
      <span>${safeText(item.detail || "--")}</span>
    </div>
  `).join("");
  const preflight = state.gatePreflight || {};
  const signalGate = preflight.signalTradeGate || {};
  const signalRows = (signalGate.queue || []).map((item) => `
    <div class="gate-readiness-item ${signalGate.signalActive ? "ok" : "blocked"}">
      <strong>${safeText(item.ticker || "--")}</strong>
      <span>${safeText(item.stage || item.section || "--")} · 分 ${Math.round(Number(item.score) || 0)} · 准备 ${Math.round(Number(item.readiness) || 0)}</span>
    </div>
  `).join("");
  const strategyAudit = preflight.strategyAudit || state.professionalSystem?.strategyAudit || {};
  const strategyCounts = strategyAudit.counts || {};
  const rejectedRows = (strategyAudit.rejected || []).slice(0, 6).map((item) => `
    <div class="gate-readiness-item blocked">
      <strong>${safeText(item.ticker || "--")}</strong>
      <span>${safeText((item.reasons || []).slice(0, 2).join("；") || "未通过策略闸门")}</span>
    </div>
  `).join("");
  const systemRows = (state.professionalSystem?.modules || []).map((item) => `
    <div class="gate-readiness-item ${item.ready ? "ok" : "blocked"}">
      <strong>${safeText(item.name || "--")}</strong>
      <span>${safeText(item.state || "--")} · ${safeText(item.detail || "--")}</span>
    </div>
  `).join("");
  setHTML("#gatePrivateBox", privateStatus ? `
    <article class="gate-private-row ${privateStatus.liveTradingRequested ? "danger" : privateStatus.authenticated ? "good" : "watch"}">
      <div>
        <strong>Gate 私有 API</strong>
        <span>${safeText(privateStatus.message || "等待验证")}</span>
      </div>
      <div>
        <strong>${safeText(privateStatus.keyMasked || "--")}</strong>
        <span>Key</span>
      </div>
      <div>
        <strong>${privateStatus.liveTradingRequested ? "已拦截" : privateStatus.liveTradingEnabled ? "开启" : "关闭"}</strong>
        <span>实盘开单</span>
      </div>
    </article>
    <div class="gate-risk-grid">
      ${riskRows || '<div class="empty compact">等待风控清单</div>'}
    </div>
    <div class="gate-protection-grid">
      ${protectionRows || '<div class="empty compact">等待三层保护策略</div>'}
    </div>
    <div class="gate-readiness-grid">
      ${readinessRows || '<div class="empty compact">等待手动实盘准入清单</div>'}
    </div>
    <article class="gate-private-row ${signalGate.signalActive ? "watch" : "danger"}">
      <div>
        <strong>信号联动交易闸门</strong>
        <span>${safeText(signalGate.reason || "等待预检")}</span>
      </div>
      <div>
        <strong>${signalGate.signalActive ? "待确认" : "自动关闭"}</strong>
        <span>入仓信号</span>
      </div>
      <div>
        <strong>${preflight.canSubmitOrder ? "可提交" : "禁止提交"}</strong>
        <span>实盘订单</span>
      </div>
    </article>
    <div class="gate-readiness-grid">
      ${signalRows || '<div class="empty compact">入仓信号消失，交易闸门已关闭。</div>'}
    </div>
    <article class="gate-private-row ${strategyCounts.allowed ? "good" : "watch"}">
      <div>
        <strong>专业策略闸门</strong>
        <span>候选 ${strategyCounts.candidates || 0} · 通过 ${strategyCounts.allowed || 0} · 拒绝 ${strategyCounts.rejected || 0}</span>
      </div>
      <div>
        <strong>${strategyAudit.dashboardFresh ? "新鲜" : "等待"}</strong>
        <span>数据状态</span>
      </div>
      <div>
        <strong>${strategyCounts.allowed ? "允许纸仓" : "只观察"}</strong>
        <span>执行结论</span>
      </div>
    </article>
    <div class="gate-readiness-grid">
      ${rejectedRows || '<div class="empty compact">暂无拒绝项或等待策略审计。</div>'}
    </div>
    <article class="gate-private-row watch">
      <div>
        <strong>专业自动交易系统</strong>
        <span>${safeText(state.professionalSystem?.profile || "professional-auto-trading-framework")}</span>
      </div>
      <div>
        <strong>${state.professionalSystem?.fileScan?.count || "--"}</strong>
        <span>已检查文件</span>
      </div>
      <div>
        <strong>${state.professionalSystem?.liveReadiness?.canSubmitOrder ? "可提交" : "预检锁定"}</strong>
        <span>实盘 API</span>
      </div>
    </article>
    <div class="gate-readiness-grid">
      ${systemRows || '<div class="empty compact">等待专业系统审计报告。</div>'}
    </div>
  ` : '<div class="empty compact">Gate Key 未写入前端；等待后端状态快照。</div>');
  $("#exchangeList").innerHTML = EXCHANGE_CONNECTORS.map((item) => {
    const isLive = item.id === "gate"
      ? Boolean(state.gateMarkets.length)
      : item.id === "binance"
        ? Boolean(state.exchangeMarkets?.venues?.binance?.online || state.dashboard?.generatedAt || state.alpha?.updatedAt)
        : item.id === "okx"
          ? Boolean(state.exchangeMarkets?.venues?.okx?.online)
        : false;
    const status = isLive ? "公开在线" : "等待公开快照";
    const tone = isLive ? "good" : "watch";
    return `
      <article class="exchange-row ${tone}">
        <span>${status}</span>
        <div>
          <strong>${item.name}</strong>
          <small>${item.scope}</small>
        </div>
        <div>
          <strong>只读</strong>
          <small>API Key 不在前端保存</small>
        </div>
      </article>
    `;
  }).join("");
  renderMyApiPanel();
}

function renderMyApiPanel() {
  const privateStatus = state.gatePrivate || {};
  const preflight = state.gatePreflight || {};
  const paper = state.paperTrading || {};
  const venues = state.exchangeMarkets?.venues || {};
  const onlineVenues = Object.values(venues).filter((item) => item.online).length;
  const blockers = preflight.blockers || [];
  setText("#myApiState", privateStatus.authenticated ? "已接入" : privateStatus.configured ? "待验证" : "未绑定");
  setText("#myApiGate", privateStatus.authenticated ? "已验证" : privateStatus.configured ? "待验证" : "未绑定");
  setText("#myApiVenues", `${onlineVenues || 0}/3`);
  setText("#myApiLive", preflight.canSubmitOrder ? "可提交" : "锁定");
  setText("#myApiPaper", paper.state === "running" ? "运行中" : "待机");
  const rows = [
    {
      name: "Gate 私有 API",
      state: privateStatus.authenticated ? "已验证" : privateStatus.configured ? "待验证" : "未绑定",
      detail: privateStatus.message || "Key 不保存在前端",
      tone: privateStatus.authenticated ? "good" : "watch",
    },
    {
      name: "Binance / OKX / Gate 公开源",
      state: `${onlineVenues || 0}/3 在线`,
      detail: "行情、合约、资金费率每 30 秒同步",
      tone: onlineVenues >= 3 ? "good" : "watch",
    },
    {
      name: "实盘订单接口",
      state: preflight.orderEndpointEnabled ? "开启" : "关闭",
      detail: blockers.length ? blockers.join("；") : "通过预检后仍需人工确认",
      tone: preflight.canSubmitOrder ? "good" : "danger",
    },
    {
      name: "自动纸交易",
      state: paper.state || "等待",
      detail: paper.reason || "信号出现自动纸仓，信号消失自动关闭",
      tone: paper.state === "running" ? "good" : "watch",
    },
  ];
  setHTML("#myApiList", rows.map((item) => `
    <article class="api-account-row ${item.tone}">
      <div>
        <strong>${safeText(item.name)}</strong>
        <span>${safeText(item.detail)}</span>
      </div>
      <small>${safeText(item.state)}</small>
    </article>
  `).join(""));
}

async function refreshGatePrivateStatus() {
  if (LOCAL_FILE_MODE) {
    state.gatePrivate = {
      configured: true,
      authenticated: false,
      keyMasked: "后端保存",
      liveTradingEnabled: false,
      message: "本地文件模式不读取私有状态；用下载链接打开会显示后端验证结果。",
    };
    renderExchangeCenter();
    return;
  }
  try {
    const response = await fetch(GATE_PRIVATE_STATUS_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Gate私有状态 HTTP ${response.status}`);
    state.gatePrivate = await response.json();
  } catch (error) {
    state.gatePrivate = {
      configured: false,
      authenticated: false,
      keyMasked: "",
      liveTradingEnabled: false,
      message: `Gate 私有状态读取失败：${error.message}`,
    };
  }
  renderExchangeCenter();
}

async function refreshGateTradePreflight() {
  if (LOCAL_FILE_MODE) {
    state.gatePreflight = {
      mode: "local-file",
      canSubmitOrder: false,
      orderEndpointEnabled: false,
      blockers: ["本地文件预览不读取交易预检"],
      signalTradeGate: {
        signalActive: false,
        state: "auto-closed",
        reason: "本地文件模式下交易闸门保持关闭",
        realOrderSyncEnabled: false,
      },
    };
    renderExchangeCenter();
    renderEntrySignals();
    renderOpenOrders();
    renderTradeDesk();
    renderProGuard();
    return;
  }
  try {
    const response = await fetch(GATE_TRADE_PREFLIGHT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Gate预检 HTTP ${response.status}`);
    state.gatePreflight = await response.json();
  } catch (error) {
    state.gatePreflight = {
      mode: "error",
      canSubmitOrder: false,
      orderEndpointEnabled: false,
      blockers: [error.message],
      signalTradeGate: {
        signalActive: false,
        state: "auto-closed",
        reason: `交易预检读取失败：${error.message}`,
        realOrderSyncEnabled: false,
      },
    };
  }
  renderExchangeCenter();
  renderEntrySignals();
  renderOpenOrders();
  renderTradeDesk();
  renderProGuard();
}

async function refreshPaperTradingState() {
  if (LOCAL_FILE_MODE) {
    state.paperTrading = {
      state: "local-file",
      realTradingEnabled: false,
      canSubmitOrder: false,
      orderEndpointEnabled: false,
      positions: [],
      summary: { openPositions: 0, closedTrades: 0, totalUnrealizedUsdt: 0 },
    };
    renderPaperTradePlan();
    renderOpenOrders();
    renderEntrySignals();
    renderNavMeta();
    return;
  }
  try {
    const response = await fetch(PAPER_TRADING_STATE_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`纸交易状态 HTTP ${response.status}`);
    state.paperTrading = await response.json();
  } catch {
    state.paperTrading = {
      state: "waiting",
      realTradingEnabled: false,
      canSubmitOrder: false,
      orderEndpointEnabled: false,
      positions: [],
      summary: { openPositions: 0, closedTrades: 0, totalUnrealizedUsdt: 0 },
    };
  }
  renderPaperTradePlan();
  renderOpenOrders();
  renderEntrySignals();
  renderNavMeta();
}

async function refreshProfessionalSystem() {
  if (LOCAL_FILE_MODE) {
    state.professionalSystem = {
      profile: "local-preview",
      fileScan: { count: 0, requiredReady: false },
      modules: [],
      liveReadiness: { canSubmitOrder: false, orderEndpointEnabled: false, blockers: ["本地文件预览"] },
    };
    renderExchangeCenter();
    return;
  }
  try {
    const response = await fetch(PROFESSIONAL_SYSTEM_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`专业系统审计 HTTP ${response.status}`);
    state.professionalSystem = await response.json();
  } catch (error) {
    state.professionalSystem = {
      profile: "waiting",
      fileScan: { count: 0, requiredReady: false },
      modules: [{ name: "专业系统审计", ready: false, state: "waiting", detail: error.message }],
      liveReadiness: { canSubmitOrder: false, orderEndpointEnabled: false, blockers: [error.message] },
    };
  }
  renderExchangeCenter();
  renderNavMeta();
}

async function refreshEmaCross4h() {
  if (LOCAL_FILE_MODE) {
    state.emaCross4h = window.WUKONG_EMA_CROSS_4H || {
      generatedAt: "",
      symbolsScanned: 0,
      matches: 0,
      items: [],
    };
    renderEmaCross4h();
    return;
  }
  try {
    const response = await fetch(EMA_CROSS_4H_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`EMA扫描 HTTP ${response.status}`);
    state.emaCross4h = await response.json();
  } catch {
    state.emaCross4h = {
      generatedAt: "",
      symbolsScanned: 0,
      matches: 0,
      items: [],
    };
  }
  renderEmaCross4h();
}

function venueField(venue, field, candidates) {
  const source = venue?.[field] || {};
  for (const key of candidates) {
    const value = source[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}

function exchangeVenueStatus(venue) {
  if (!venue) return "等待";
  if (venue.spot || venue.futures || venue.funding) return venue.errors?.length ? "部分在线" : "在线";
  return venue.errors?.length ? "异常" : "等待";
}

function renderExchangeApi() {
  const snapshot = state.exchangeMarkets;
  const markets = snapshot?.markets || [];
  const venues = snapshot?.venues || {};
  const online = Object.values(venues).filter((item) => item.online).length;
  setText("#exchangeApiStatus", markets.length ? `快照 ${fmtTime(snapshot.generatedAt)}` : "等待同步");
  setText("#exchangeApiVenues", `${online}/3`);
  setText("#exchangeApiPairs", `${markets.length || GATE_PAIRS.length}`);
  setText("#exchangeApiFreshness", snapshot?.generatedAt ? fmtAge(snapshot.generatedAt) : "--");
  if (!markets.length) {
    setHTML("#exchangeApiList", '<div class="empty compact">等待 Binance / OKX / Gate API 快照</div>');
    renderNavMeta();
    return;
  }
  const rows = markets.flatMap((market) => {
    const labels = [
      ["binance", "Binance"],
      ["okx", "OKX"],
      ["gate", "Gate"],
    ];
    return labels.map(([key, label]) => {
      const venue = market.venues?.[key] || {};
      const spot = venueField(venue, "spot", ["lastPrice", "last", "last_price"]);
      const change = venueField(venue, "spot", ["priceChangePercent", "change_percentage", "sodUtc8"]);
      const futures = venueField(venue, "futures", ["lastPrice", "markPrice", "mark_price", "last"]);
      const funding = venueField(venue, "funding", ["lastFundingRate", "fundingRate", "funding_rate"]);
      const status = exchangeVenueStatus(venue);
      const tone = status === "在线" ? "good" : status === "部分在线" ? "watch" : "danger";
      return `
        <article class="exchange-api-row ${tone}">
          <div>
            <strong>${label}</strong>
            <span>${market.pair || `${market.symbol}/USDT`}</span>
          </div>
          <div>
            <strong>${fmtPrice(spot)}</strong>
            <span>现货</span>
          </div>
          <div>
            <strong class="${scoreClass(change)}">${fmtPct(change)}</strong>
            <span>24h</span>
          </div>
          <div>
            <strong>${fmtPrice(futures)}</strong>
            <span>合约</span>
          </div>
          <div>
            <strong class="${scoreClass(funding)}">${fmtFunding(funding)}</strong>
            <span>资金费率</span>
          </div>
          <div>
            <strong>${status}</strong>
            <span>${venue.errors?.length ? "有错误" : "只读"}</span>
          </div>
        </article>
      `;
    });
  });
  setHTML("#exchangeApiList", rows.join(""));
  renderNavMeta();
}

function renderContractLaunchRadar() {
  const rows = contractLaunchItems();
  $("#contractLaunchCount").textContent = rows.length ? `${rows.length} 个` : "等待";
  if (!rows.length) {
    $("#contractLaunchList").innerHTML = '<div class="empty compact">等待 OI 异动、入场窗口或 Alpha 映射信号</div>';
    return;
  }
  $("#contractLaunchList").innerHTML = rows.slice(0, 3).map((item) => {
    const metric = tokenMetric(item);
    const score = Math.round(signalScore(item));
    return `
      <article class="contract-launch-row">
        <div>
          <strong>${metric.ticker}</strong>
          <span>${metric.stage} · ${compactText(metric.structure, 56)}</span>
        </div>
        <div>
          <strong class="${scoreClass(metric.change)}">${fmtPct(metric.change)}</strong>
          <span>OI ${fmtPct(metric.oi)} · 分 ${score}</span>
        </div>
        <button class="watch-button" type="button" data-paper-order="${metric.ticker}">模拟单</button>
      </article>
    `;
  }).join("");
}

function renderEntrySignals() {
  const signalGate = state.gatePreflight?.signalTradeGate || {};
  const rows = signalGate.queue || [];
  const rejected = signalGate.rejected || state.gatePreflight?.strategyAudit?.rejected || [];
  setText("#entrySignalStatus", signalGate.signalActive ? `${rows.length} 个信号` : "无入仓信号");
  if (!rows.length) {
    const rejectedHtml = rejected.slice(0, 4).map((item) => `
      <article class="entry-signal-row">
        <div>
          <strong>${safeText(item.ticker || "--")}</strong>
          <span>${safeText(item.stage || "候选")}</span>
        </div>
        <div>
          <strong>${Math.round(Number(item.readiness) || 0)}</strong>
          <span>准备度</span>
        </div>
        <div>
          <strong>拒绝</strong>
          <span>${safeText((item.reasons || []).slice(0, 1).join("；") || "未过闸门")}</span>
        </div>
      </article>
    `).join("");
    setHTML("#entrySignalList", rejectedHtml || '<div class="empty compact">当前没有入仓信号，交易闸门自动关闭。</div>');
    return;
  }
  setHTML("#entrySignalList", rows.slice(0, 8).map((item, index) => {
    const ticker = String(item.ticker || "--").toUpperCase();
    const score = Math.round(Number(item.score) || 0);
    const isPrimary = index === 0;
    const position = (state.paperTrading?.positions || []).find((row) => String(row.market || "").replace("_USDT", "") === ticker);
    return `
      <article class="entry-signal-row ${isPrimary ? "primary" : ""}">
        <div>
          <strong>${ticker}</strong>
          <span>${safeText(item.stage || item.section || "--")}</span>
        </div>
        <div>
          <strong>${score}</strong>
          <span>信号分</span>
        </div>
        <div>
          <strong>${position ? "已开纸仓" : isPrimary ? "待确认" : "观察"}</strong>
          <span>准备 ${Math.round(Number(item.readiness) || 0)} · ${safeText(item.section || "signal")}</span>
        </div>
      </article>
    `;
  }).join(""));
}

function renderOpenOrders() {
  const positions = state.paperTrading?.positions || [];
  setText("#openOrderStatus", positions.length ? `${positions.length} 笔纸仓` : "无开单");
  if (!positions.length) {
    setHTML("#openOrderList", '<div class="empty compact">当前没有已开纸仓；真实订单接口关闭。</div>');
    return;
  }
  setHTML("#openOrderList", positions.map((item) => {
    const tiers = (item.takeProfitTiers || []).map((tier, index) => `T${index + 1} +${tier.triggerPct}%/${tier.closePct}%`).join(" · ");
    const filled = item.filledTakeProfits || [];
    return `
      <article class="open-order-row">
        <div>
          <strong>${safeText(item.market || "--")}</strong>
          <span>${safeText(item.side || "--")} · ${safeText(item.state || "--")}</span>
        </div>
        <div>
          <strong>${fmtPrice(item.entryPrice)}</strong>
          <span>入场价</span>
        </div>
        <div>
          <strong>${fmtPrice(item.lastPrice)}</strong>
          <span>现价</span>
        </div>
        <div>
          <strong>${Number(item.maxMarginUsdt || 0).toFixed(2)}U</strong>
          <span>保证金</span>
        </div>
        <div>
          <strong>${Number(item.maxNotionalUsdt || 0).toFixed(2)}U</strong>
          <span>名义</span>
        </div>
        <div>
          <strong class="${scoreClass(item.unrealizedPct)}">${fmtSignedPct(item.unrealizedPct)}</strong>
          <span>${Number(item.unrealizedUsdt || 0).toFixed(4)}U</span>
        </div>
        <p>剩余 ${Number(item.remainingPct ?? 100).toFixed(0)}% · 已止盈 ${filled.length}/${(item.takeProfitTiers || []).length} · 止损 ${item.stopLossPct || "--"}%-${item.maxStopLossPct || "--"}% · ${tiers || "等待止盈计划"} · 真实订单关闭</p>
      </article>
    `;
  }).join(""));
}

function renderEmaCross4h() {
  const snapshot = state.emaCross4h || {};
  const rows = snapshot.items || [];
  setText("#emaCrossStatus", snapshot.generatedAt ? `${rows.length} 个 · ${fmtAge(snapshot.generatedAt)}` : "等待扫描");
  if (!rows.length) {
    setHTML("#emaCrossList", '<div class="empty compact">当前没有 4H EMA21 上穿 EMA55 的币种。</div>');
    return;
  }
  setHTML("#emaCrossList", rows.slice(0, 80).map((item) => `
    <article class="ema-cross-row">
      <div>
        <strong>${safeText(item.ticker || "--")}</strong>
        <span>${safeText(item.pair || item.symbol || "--")}</span>
      </div>
      <div>
        <strong>${fmtPrice(item.close)}</strong>
        <span>收盘价</span>
      </div>
      <div>
        <strong class="${scoreClass(item.changeLastCandlePct)}">${fmtPct(item.changeLastCandlePct)}</strong>
        <span>4H涨跌</span>
      </div>
      <div>
        <strong>${fmtPrice(item.ema21)}</strong>
        <span>EMA21</span>
      </div>
      <div>
        <strong>${fmtPrice(item.ema55)}</strong>
        <span>EMA55</span>
      </div>
      <div>
        <strong class="${scoreClass(item.emaSpreadPct)}">${fmtPct(item.emaSpreadPct)}</strong>
        <span>间距</span>
      </div>
    </article>
  `).join(""));
}

function renderPaperTradePlan(item = contractLaunchItems()[0]) {
  const plan = paperPlanFor(item);
  const engine = state.paperTrading || {};
  const position = (engine.positions || [])[0];
  if (!plan) {
    $("#paperTradePlan").innerHTML = '<div class="empty compact">等待合约启动候选后生成模拟单</div>';
    $("#paperTradeStatus").textContent = "只生成模拟订单，不调用交易所私有 API。";
    return;
  }
  $("#paperTradeStatus").textContent = position
    ? `${position.market} 自动纸仓运行中；真实订单关闭。`
    : `${plan.ticker} 模拟方案已生成；不会真实下单。`;
  $("#paperTradePlan").innerHTML = `
    <div><strong>${plan.ticker}</strong><span>模拟标的</span></div>
    <div><strong>${plan.side}</strong><span>方向</span></div>
    <div><strong>${plan.notional}</strong><span>名义仓位</span></div>
    <div><strong>${plan.leverage}</strong><span>模拟杠杆</span></div>
    <div><strong>${plan.margin || "--"}</strong><span>保证金</span></div>
    <div><strong>${plan.risk || "--"}</strong><span>风险封顶</span></div>
    <div><strong>${position ? fmtSignedPct(position.unrealizedPct) : "--"}</strong><span>纸面浮盈亏</span></div>
    <div><strong>${position ? `${Number(position.unrealizedUsdt || 0).toFixed(4)}U` : "--"}</strong><span>纸面盈亏</span></div>
    <div><strong>${plan.stop}</strong><span>模拟止损</span></div>
    <div><strong>${plan.takeProfit}</strong><span>模拟止盈</span></div>
    <p>${plan.takeProfitPlan}。${plan.stopDetail}。${plan.trigger}。自动纸交易会随信号开关；真实开单必须走后端风控、子账户 API Key、IP 白名单和人工确认。</p>
  `;
}

function renderTradeExecutionLab() {
  renderExchangeCenter();
  renderEntrySignals();
  renderOpenOrders();
  renderEmaCross4h();
  renderContractLaunchRadar();
  renderPaperTradePlan();
}

function briefText() {
  const stamp = fmtTime(state.dashboard?.generatedAt);
  const lines = ["悟空 · 今日先读", `行情：${stamp}`, ""];
  for (const row of state.briefRows || []) {
    lines.push(`${row.label}：${row.value}`);
    lines.push(`  ${row.note}`);
  }
  lines.push("", "只做公开研究信号，不构成投资建议。");
  return lines.join("\n");
}

async function copyBrief() {
  const button = $("#copyBrief");
  const original = button.textContent;
  try {
    const text = briefText();
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = document.createElement("textarea");
      area.value = text;
      area.setAttribute("readonly", "");
      area.style.position = "fixed";
      area.style.left = "-9999px";
      document.body.appendChild(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    button.textContent = "已复制";
  } catch {
    button.textContent = "复制失败";
  } finally {
    window.setTimeout(() => {
      button.textContent = original;
    }, 3200);
  }
}

async function copyText(value) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const area = document.createElement("textarea");
  area.value = value;
  area.setAttribute("readonly", "");
  area.style.position = "fixed";
  area.style.left = "-9999px";
  document.body.appendChild(area);
  area.select();
  document.execCommand("copy");
  area.remove();
}

async function copyTelegramCommand(button) {
  const command = button.dataset.command || "";
  if (!command) return;
  const original = button.textContent;
  try {
    await copyText(command);
    button.textContent = "已复制";
    setText("#telegramCommandStatus", command);
  } catch {
    button.textContent = "复制失败";
    setText("#telegramCommandStatus", "复制失败");
  } finally {
    window.setTimeout(() => {
      button.textContent = original;
    }, 2200);
  }
}

function shareLinks() {
  const origin = window.location.origin;
  const base = `${origin}${window.location.pathname.replace(/\/[^/]*$/, "")}`;
  return {
    ios: `${base}/install.html?v=${APP_VERSION}`,
    android: `${base}/downloads/wukong-android-release.apk?v=${APP_VERSION}`,
    web: `${base}/index.html?v=${APP_VERSION}`,
  };
}

function shareText(kind) {
  const links = shareLinks();
  if (kind === "ios") return links.ios;
  if (kind === "android") return links.android;
  if (kind === "web") return links.web;
  return [
    "悟空 APP 下载",
    `苹果/iPhone：${links.ios}`,
    `安卓/Android：${links.android}`,
    `网页端：${links.web}`,
  ].join("\n");
}

function updateTelegramShareLink() {
  const link = $("#shareTelegramDownload");
  if (!link) return;
  const links = shareLinks();
  const params = new URLSearchParams({
    url: links.ios,
    text: shareText("all"),
  });
  link.href = `https://t.me/share/url?${params.toString()}`;
}

async function copyShareLink(button) {
  const kind = button.dataset.shareLink || "all";
  const original = button.textContent;
  try {
    await copyText(shareText(kind));
    button.textContent = "已复制";
    setText("#shareStatus", kind === "all" ? "全部链接" : "链接已复制");
  } catch {
    button.textContent = "复制失败";
    setText("#shareStatus", "复制失败");
  } finally {
    window.setTimeout(() => {
      button.textContent = original;
    }, 2200);
  }
}

function currentItems() {
  const dashboard = state.dashboard || {};
  if (state.section === "risk") {
    return [...(dashboard.delistRiskWatch || []), ...(dashboard.overheated || [])];
  }
  return dashboard[state.section] || [];
}

function renderNavMeta() {
  const counts = state.dashboard?.counts || {};
  const riskCount = (counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length);
  const priorityCount = priorityItems().length;
  const launchCount = contractLaunchItems().length;
  const queueCount = state.telegramStatus?.queueTotal ?? telegramQueueItems().length;
  const healthRows = state.downloadHealth || [];
  const healthOk = healthRows.filter((item) => item.ok).length;
  const gateState = state.gatePrivate?.authenticated ? "Gate已验" : state.gatePrivate?.configured ? "Gate待验" : "API未绑";
  const paperState = state.paperTrading?.state === "running" ? "纸仓运行" : "纸仓待机";
  $("#navOverviewMeta").textContent = `${state.dataMode || "连接中"} · ${counts.tickers ?? "--"} 币 · 风险 ${riskCount}`;
  $("#navDecisionMeta").textContent = `${priorityCount} 优先 · ${state.watchlist.length} 关注`;
  const apiVenues = Object.values(state.exchangeMarkets?.venues || {}).filter((item) => item.online).length || 3;
  $("#navMarketMeta").textContent = `${launchCount} 合约 · API ${apiVenues}/3`;
  $("#navTelegramMeta").textContent = `${queueCount || 0} 队列 · ${state.telegramStatus?.status === "error" ? "异常" : "运行中"}`;
  $("#navInstallMeta").textContent = `${gateState} · ${paperState}`;
  $("#navFilesMeta").textContent = state.fileSync?.fileCount ? `${state.fileSync.fileCount} 文件` : "等待清单";
}

function renderProGuard() {
  const counts = state.dashboard?.counts || {};
  const riskCount = (counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length);
  const priorityCount = priorityItems().length;
  const launchCount = contractLaunchItems().length;
  const queueCount = state.telegramStatus?.queueTotal ?? telegramQueueItems().length;
  const fileCount = state.fileSync?.fileCount || 0;
  const healthRows = state.downloadHealth || [];
  const healthOk = healthRows.filter((item) => item.ok).length;
  const dashboardTime = state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const signalGate = state.gatePreflight?.signalTradeGate || {};
  const signalActive = Boolean(signalGate.signalActive);
  const blockerCount = state.gatePreflight?.blockers?.length || 0;
  const ageText = dashboardTime ? fmtAge(dashboardTime) : "等待同步";
  const isFresh = dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000;
  const score = Math.max(0, Math.min(100,
    (isFresh ? 40 : 18) +
    (riskCount ? Math.max(0, 28 - riskCount * 2) : 30) +
    (priorityCount ? 16 : 6) +
    (fileCount ? 8 : 0) +
    (healthRows.length && healthOk === healthRows.length ? 6 : 0)
  ));
  setText("#freshnessScore", `${state.dataMode || "连接中"} · ${ageText}`);
  setText("#dataFreshnessGuard", isFresh ? "新鲜" : "需关注");
  setText("#riskGuard", riskCount ? `${riskCount} 风险` : "正常");
  setText("#executionGuard", signalActive ? "信号待确认" : "信号关闭");
  setText("#autoUpdateGuard", "30秒循环");
  setText("#dataGate", isFresh ? "通过" : "等待");
  setText("#signalGate", signalActive ? "有信号" : "已关闭");
  setText("#riskGate", blockerCount ? `${blockerCount} 阻断` : (riskCount ? `${riskCount} 风险` : "通过"));
  setText("#tradeGate", signalActive ? "待确认" : "自动关闭");
  renderMissionBeacon({ isFresh, score, riskCount, priorityCount, ageText });
  renderCommandAlert({ isFresh, score, riskCount, priorityCount, launchCount, ageText });
  renderUpdateSla({ isFresh, dashboardTime, ageText, score });
}

function renderCommandAlert(context = {}) {
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const metric = primary ? tokenMetric(primary) : {};
  let tone = "等待";
  let title = "等待首次同步";
  let body = "页面会自动刷新，并在数据到达后给出主结论。";
  let next = "实盘开单保持关闭。";
  let commandState = "waiting";
  if (context.isFresh && context.riskCount) {
    tone = "风控优先";
    title = `${context.riskCount} 个风险项，禁止追高`;
    body = `${context.priorityCount || 0} 个优先候选、${context.launchCount || 0} 个合约启动信号，先看风控再看机会。`;
    next = primary ? `第一关注 ${metric.ticker || primary.ticker || "--"}，只允许观察或纸交易复核。` : "只允许观察或纸交易复核。";
    commandState = "risk";
  } else if (context.isFresh && context.priorityCount) {
    tone = "机会观察";
    title = `${context.priorityCount} 个优先候选`;
    body = "数据新鲜，候选存在，但仍需等待回踩、确认和风控通过。";
    next = primary ? `第一关注 ${metric.ticker || primary.ticker || "--"}，不自动开单。` : "不自动开单。";
    commandState = "ready";
  } else if (context.isFresh) {
    tone = "自动巡航";
    title = "暂无高优先动作";
    body = "系统保持自动巡航，等待下一轮信号进入队列。";
    next = "继续观察，30秒循环同步。";
    commandState = "ready";
  }
  $("#commandTone").textContent = tone;
  $("#commandTitle").textContent = title;
  $("#commandBody").textContent = body;
  $("#commandNext").textContent = next;
  document.body.dataset.commandState = commandState;
}

function renderMissionBeacon(context = {}) {
  const mode = context.isFresh ? (context.riskCount ? "风控巡航" : "机会观察") : "等待同步";
  const detail = context.isFresh
    ? `${context.score ?? "--"}/100 · 风险 ${context.riskCount || 0} · 实盘关闭`
    : "数据未新鲜 · 等待自动同步";
  $("#missionState").textContent = mode;
  $("#missionDetail").textContent = detail;
  document.body.dataset.mission = context.isFresh ? (context.riskCount ? "risk" : "ready") : "waiting";
}

function renderOperatorBrief(context = {}) {
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const hasSignal = Boolean(primary);
  const metric = hasSignal ? tokenMetric(primary) : {};
  const riskText = context.riskCount ? `${context.riskCount} 风险项` : "风险正常";
  const primaryName = hasSignal ? String(metric.ticker || primary.ticker || "--").toUpperCase() : "--";
  const stage = hasSignal ? (metric.stage || primary.stage || "观察") : "等待信号";
  const structure = hasSignal ? (metric.structure || primary.primaryOpportunityLane || "候选") : "自动巡航";
  const actionText = hasSignal ? nextAction(primary) : "等待下一轮自动刷新，先保持观察。";
  const verdict = context.isFresh
    ? (context.riskCount ? "有机会，但先过风控" : "数据新鲜，可以观察候选")
    : "数据未新鲜，先等同步";
  $("#operatorVerdict").textContent = verdict;
  $("#operatorPrimary").textContent = hasSignal ? `${primaryName} · ${stage}` : "--";
  $("#operatorPrimaryNote").textContent = hasSignal ? `${structure} · ${riskText}` : "等待候选进入队列";
  $("#operatorNext").textContent = context.riskCount ? "先风控" : (hasSignal ? "看回踩确认" : "等待同步");
  $("#operatorNextNote").textContent = actionText;
  $("#operatorBlock").textContent = "禁止实盘自动开单";
  $("#operatorTrust").textContent = context.isFresh ? `可信度 ${context.score ?? "--"}/100 · ${context.ageText}` : "可信度等待同步";
}

function renderConfidenceStrip(context = {}) {
  const sourceLabel = state.dataMode || "连接中";
  const gateCount = state.gateMarkets.length || GATE_PAIRS.length;
  const syncOk = context.healthTotal ? `${context.healthOk}/${context.healthTotal}` : "等待";
  $("#confidenceData").textContent = context.isFresh ? `${sourceLabel} · 新鲜` : `${sourceLabel} · 待确认`;
  $("#confidenceDataNote").textContent = `数据 ${context.ageText || "等待"} · Gate ${gateCount} 组`;
  $("#confidenceSignal").textContent = `${context.priorityCount || 0} 优先 · ${context.launchCount || 0} 合约`;
  $("#confidenceSignalNote").textContent = context.priorityCount ? "有候选，仍需回踩/确认" : "暂无高优先动作";
  $("#confidenceRisk").textContent = context.riskCount ? `${context.riskCount} 风险拦截` : "纪律通过";
  $("#confidenceRiskNote").textContent = context.riskCount ? "风险项禁止追高" : "风险池未升高";
  $("#confidenceSync").textContent = `${context.fileCount || "--"} 文件 · ${syncOk}`;
  $("#confidenceSyncNote").textContent = `TG ${context.queueCount || 0} · v${APP_VERSION}`;
}

function renderAuditTrail(context = {}) {
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const metric = primary ? tokenMetric(primary) : {};
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const decision = context.riskCount ? "风控优先" : (primary ? "候选观察" : "等待信号");
  $("#auditRefresh").textContent = state.lastRefreshAt ? new Date(state.lastRefreshAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }) : "--";
  $("#auditRefreshNote").textContent = context.dashboardTime ? `行情 ${fmtAge(context.dashboardTime)}` : "等待行情时间";
  $("#auditSource").textContent = state.dataMode || "连接中";
  $("#auditSourceNote").textContent = context.isFresh ? "数据通过新鲜度检查" : "等待下一轮同步";
  $("#auditDecision").textContent = decision;
  $("#auditDecisionNote").textContent = primary ? `${metric.ticker || primary.ticker || "--"} · ${metric.stage || "观察"}` : "无候选时保持空仓观察";
  $("#auditNext").textContent = `${nextSeconds}秒`;
  $("#auditNextNote").textContent = `v${APP_VERSION} · 实盘关闭`;
}

function renderDisciplineRail(context = {}) {
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const mode = context.isFresh ? (context.riskCount ? "风控巡航" : "机会观察") : "等待同步";
  const allowed = context.priorityCount ? "观察 / 纸交易复核" : "观察 / 等待信号";
  $("#disciplineMode").textContent = mode;
  $("#disciplineAllowed").textContent = allowed;
  $("#disciplineBlocked").textContent = "实盘自动开单";
  $("#disciplineCadence").textContent = `${nextSeconds}秒循环`;
}

function renderUpdateSla(context = {}) {
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const ageMs = dashboardTime ? Date.now() - new Date(dashboardTime).getTime() : Infinity;
  const isFresh = context.isFresh ?? (Number.isFinite(ageMs) && ageMs < 10 * 60_000);
  const isStale = !Number.isFinite(ageMs) || ageMs >= 10 * 60_000;
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const cycleText = state.refreshInFlight ? "同步中" : "自动巡航";
  const networkText = navigator.onLine ? "在线" : "离线";
  const staleText = isFresh ? "新鲜" : "需关注";
  setText("#updateCycle", cycleText);
  setText("#updateCycleNote", state.refreshInFlight ? "正在拉取最新数据" : `${nextSeconds}秒后自动同步`);
  setText("#networkGuard", networkText);
  setText("#networkGuardNote", navigator.onLine ? "网络正常，后台自动补齐" : "离线，恢复后自动刷新");
  setText("#staleGuard", staleText);
  setText("#staleGuardNote", isStale ? `数据 ${context.ageText || fmtAge(dashboardTime)}` : "10分钟内有效");
  setText("#releaseGuard", `v${APP_VERSION}`);
  setText("#releaseGuardNote", state.lastRefreshError ? "上轮同步有错误" : "缓存和二维码同步");
  setText("#auditNext", `${nextSeconds}秒`);
  setText("#disciplineCadence", `${nextSeconds}秒循环`);
  document.body.dataset.opsHealth = !navigator.onLine || isStale || state.lastRefreshError ? "warn" : "good";
}

function renderOpsMatrix(context = {}) {
  const counts = state.dashboard?.counts || {};
  const riskCount = context.riskCount ?? ((counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length));
  const priorityCount = context.priorityCount ?? priorityItems().length;
  const launchCount = context.launchCount ?? contractLaunchItems().length;
  const queueCount = context.queueCount ?? (state.telegramStatus?.queueTotal ?? telegramQueueItems().length);
  const fileCount = context.fileCount ?? (state.fileSync?.fileCount || 0);
  const healthRows = state.downloadHealth || [];
  const healthOk = context.healthOk ?? healthRows.filter((item) => item.ok).length;
  const healthTotal = context.healthTotal ?? healthRows.length;
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const ageText = context.ageText || fmtAge(dashboardTime);
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const linkState = !navigator.onLine ? "离线" : (state.refreshInFlight ? "同步中" : (isFresh ? "稳定" : "需同步"));
  const distribution = healthTotal ? `${healthOk}/${healthTotal} 下载 · TG ${queueCount || 0}` : `TG ${queueCount || 0}`;
  const summary = isFresh
    ? `数据 ${ageText}，${priorityCount} 个优先候选，${launchCount} 个合约启动，${riskCount} 个风险项，${nextSeconds} 秒后自动刷新。`
    : `数据 ${ageText || "等待同步"}，系统保持自动刷新，实盘开单继续关闭。`;
  $("#opsMatrixSummary").textContent = summary;
  $("#opsMatrixLink").textContent = `${state.dataMode || "连接中"} · ${linkState}`;
  $("#opsMatrixLinkNote").textContent = isFresh ? `数据 ${ageText}` : "等待下一轮自动同步";
  $("#opsMatrixRefresh").textContent = state.refreshInFlight ? "同步中" : `${nextSeconds}秒`;
  $("#opsMatrixRefreshNote").textContent = navigator.onLine ? "在线自动巡航" : "网络恢复后补刷新";
  $("#opsMatrixDistribution").textContent = distribution;
  $("#opsMatrixDistributionNote").textContent = fileCount ? `${fileCount} 文件已同步` : "等待文件清单";
  $("#opsMatrixRisk").textContent = riskCount ? `${riskCount} 风险 · 禁追` : "纪律通过";
  $("#opsMatrixRiskNote").textContent = priorityCount ? `${priorityCount} 优先候选仅复核` : "无候选时保持观察";
  $("#opsMatrixVersion").textContent = `v${APP_VERSION}`;
  $("#opsMatrixVersionNote").textContent = state.lastRefreshError ? "上轮同步需复查" : "缓存、二维码、下载页一致";
}

function updatePipelineStep(key, stateName, status, note) {
  const statusNode = $(`#pipeline${key}Status`);
  const noteNode = $(`#pipeline${key}Note`);
  if (!statusNode || !noteNode) return;
  statusNode.textContent = status;
  noteNode.textContent = note;
  const item = statusNode.closest("article");
  if (item) item.dataset.state = stateName;
}

function renderSyncPipeline(context = {}) {
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const ageText = context.ageText || fmtAge(dashboardTime);
  const riskCount = context.riskCount ?? ((state.dashboard?.counts?.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length));
  const priorityCount = context.priorityCount ?? priorityItems().length;
  const launchCount = context.launchCount ?? contractLaunchItems().length;
  const queueCount = context.queueCount ?? (state.telegramStatus?.queueTotal ?? telegramQueueItems().length);
  const fileCount = context.fileCount ?? (state.fileSync?.fileCount || 0);
  const healthRows = state.downloadHealth || [];
  const healthOk = context.healthOk ?? healthRows.filter((item) => item.ok).length;
  const healthTotal = context.healthTotal ?? healthRows.length;
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const cacheReady = `v${APP_VERSION}`;
  const healthLabel = healthTotal ? `${healthOk}/${healthTotal}` : "等待";
  const summary = state.refreshInFlight
    ? "正在同步新数据，完成后会自动刷新所有版块和 Telegram 队列。"
    : `流水线正常巡航，${nextSeconds} 秒后进入下一轮；当前数据 ${ageText || "等待"}。`;
  $("#pipelineSummary").textContent = summary;
  updatePipelineStep(
    "Fetch",
    state.refreshInFlight ? "active" : (state.lastRefreshAt ? "done" : "waiting"),
    state.refreshInFlight ? "拉取中" : (state.lastRefreshAt ? "完成" : "等待"),
    `${state.dataMode || "连接中"} · ${nextSeconds}秒`
  );
  updatePipelineStep(
    "Validate",
    isFresh ? "done" : "warn",
    isFresh ? "通过" : "需同步",
    isFresh ? `数据 ${ageText}` : "等待新鲜快照"
  );
  updatePipelineStep(
    "Risk",
    riskCount ? "warn" : (isFresh ? "done" : "waiting"),
    riskCount ? `${riskCount} 风险` : "通过",
    priorityCount ? `${priorityCount} 优先 · ${launchCount} 合约` : "无高优先候选"
  );
  updatePipelineStep(
    "Dispatch",
    healthTotal && healthOk === healthTotal ? "done" : "active",
    healthTotal ? `${healthLabel} 在线` : "同步中",
    `TG ${queueCount || 0} · 文件 ${fileCount || "--"}`
  );
  updatePipelineStep(
    "Cache",
    state.lastRefreshError ? "warn" : "done",
    state.lastRefreshError ? "复查" : "一致",
    `${cacheReady} · PWA 手机端`
  );
}

function tapeItem(label, value, note, tone = "neutral") {
  return `<article data-tone="${safeText(tone)}"><span>${safeText(label)}</span><strong>${safeText(value)}</strong><small>${safeText(note)}</small></article>`;
}

function renderLiveTape(context = {}) {
  const tape = $("#liveTapeItems");
  if (!tape) return;
  const counts = state.dashboard?.counts || {};
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const launch = contractLaunchItems()[0];
  const primaryMetric = primary ? tokenMetric(primary) : null;
  const launchMetric = launch ? tokenMetric(launch) : null;
  const riskCount = context.riskCount ?? ((counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length));
  const priorityCount = context.priorityCount ?? priorityItems().length;
  const launchCount = context.launchCount ?? contractLaunchItems().length;
  const queueCount = context.queueCount ?? (state.telegramStatus?.queueTotal ?? telegramQueueItems().length);
  const healthRows = state.downloadHealth || [];
  const healthOk = context.healthOk ?? healthRows.filter((item) => item.ok).length;
  const healthTotal = context.healthTotal ?? healthRows.length;
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const ageText = context.ageText || fmtAge(dashboardTime);
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const healthText = healthTotal ? `${healthOk}/${healthTotal}` : "等待";
  const rows = [
    tapeItem(
      "主线",
      primaryMetric ? `${String(primaryMetric.ticker).toUpperCase()} · ${primaryMetric.stage}` : "等待候选",
      primaryMetric ? `24h ${fmtPct(primaryMetric.change)} · OI ${fmtPct(primaryMetric.oi)}` : `${nextSeconds}秒后刷新`,
      primaryMetric ? "good" : "waiting"
    ),
    tapeItem(
      "合约",
      launchMetric ? `${String(launchMetric.ticker).toUpperCase()} · ${launchCount} 个` : "等待启动",
      launchMetric ? `分 ${launchMetric.score} · ${launchMetric.structure}` : "OI / Alpha 监控",
      launchMetric ? "good" : "waiting"
    ),
    tapeItem(
      "风险",
      riskCount ? `${riskCount} 项 · 禁追` : "纪律通过",
      priorityCount ? `${priorityCount} 优先候选仅复核` : "无候选时保持观察",
      riskCount ? "warn" : "good"
    ),
    tapeItem(
      "分发",
      `TG ${queueCount || 0} · 下载 ${healthText}`,
      isFresh ? `数据 ${ageText}` : "等待新鲜快照",
      healthTotal && healthOk === healthTotal ? "good" : "neutral"
    ),
    tapeItem(
      "版本",
      `v${APP_VERSION} · ${state.refreshInFlight ? "同步中" : "巡航"}`,
      `${nextSeconds}秒 · 实盘关闭`,
      state.lastRefreshError ? "warn" : "neutral"
    ),
  ];
  tape.innerHTML = rows.join("");
}

function entryStep(index, label, value, stateName = "waiting") {
  return `<article data-state="${safeText(stateName)}"><span>${safeText(index)}</span><strong>${safeText(label)}</strong><small>${safeText(value)}</small></article>`;
}

function renderEntryChecklist(context = {}) {
  const list = $("#entryReviewSteps");
  if (!list) return;
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const riskCount = context.riskCount ?? ((state.dashboard?.counts?.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length));
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const ageText = context.ageText || fmtAge(dashboardTime);
  if (!primary) {
    $("#entryReviewTitle").textContent = "入场复核清单";
    $("#entryReviewSummary").textContent = "暂无第一候选，保持自动巡航。";
    list.innerHTML = [
      entryStep("01", "价格", "等待候选", "waiting"),
      entryStep("02", "OI", "等待候选", "waiting"),
      entryStep("03", "信号", "等待候选", "waiting"),
      entryStep("04", "风控", "实盘关闭", "warn"),
      entryStep("05", "动作", "只观察", "waiting"),
    ].join("");
    return;
  }
  const metric = tokenMetric(primary);
  const ticker = String(metric.ticker || "--").toUpperCase();
  const change = number(metric.change, NaN);
  const oi = number(metric.oi, NaN);
  const score = number(metric.score, NaN);
  const priceState = Number.isFinite(change) && change >= 0 ? "good" : "warn";
  const oiState = Number.isFinite(oi) && oi > 0 ? "good" : "waiting";
  const signalState = Number.isFinite(score) && score >= 70 ? "good" : "neutral";
  const riskState = riskCount ? "warn" : "good";
  $("#entryReviewTitle").textContent = `${ticker} 入场复核`;
  $("#entryReviewSummary").textContent = `${metric.stage} · ${metric.structure} · 数据 ${ageText} · 不自动开单。`;
  list.innerHTML = [
    entryStep("01", "价格", `24h ${fmtPct(metric.change)}`, isFresh ? priceState : "waiting"),
    entryStep("02", "OI", `1h ${fmtPct(metric.oi)}`, oiState),
    entryStep("03", "信号", `分 ${metric.score} · ${metric.stage}`, signalState),
    entryStep("04", "风控", riskCount ? `${riskCount} 风险项，禁止追高` : "纪律通过", riskState),
    entryStep("05", "动作", nextAction(primary), riskCount ? "warn" : "neutral"),
  ].join("");
}

function riskProtocolStep(index, label, value, stateName = "waiting") {
  return `<article data-state="${safeText(stateName)}"><span>${safeText(index)}</span><strong>${safeText(label)}</strong><small>${safeText(value)}</small></article>`;
}

function renderRiskProtocol(context = {}) {
  const list = $("#riskProtocolSteps");
  if (!list) return;
  const rows = riskRadarItems();
  const riskCount = context.riskCount ?? rows.length;
  const queueCount = context.queueCount ?? (state.telegramStatus?.queueTotal ?? telegramQueueItems().length);
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const ageText = context.ageText || fmtAge(dashboardTime);
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const firstRisk = rows[0];
  const firstTicker = firstRisk?.item?.ticker ? String(firstRisk.item.ticker).toUpperCase() : "";
  const riskLabel = riskCount ? `${riskCount} 项风险` : "风险正常";
  $("#riskProtocolTitle").textContent = riskCount ? "风险处置清单" : "风险处置清单";
  $("#riskProtocolSummary").textContent = riskCount
    ? `${firstTicker ? `${firstTicker} 等风险优先处理` : "风险优先处理"} · 数据 ${ageText} · 禁止追高。`
    : `当前未发现高优先风险 · 数据 ${ageText}。`;
  list.innerHTML = [
    riskProtocolStep("01", "等级", riskLabel, riskCount ? "warn" : (isFresh ? "good" : "waiting")),
    riskProtocolStep("02", "禁止", "实盘自动开单 / 追高", "warn"),
    riskProtocolStep("03", "允许", riskCount ? "观察 / 纸交易复核" : "观察候选", riskCount ? "neutral" : "good"),
    riskProtocolStep("04", "复核", `${nextSeconds}秒后自动复查`, isFresh ? "good" : "waiting"),
    riskProtocolStep("05", "同步", `TG ${queueCount || 0} · v${APP_VERSION}`, queueCount ? "good" : "neutral"),
  ].join("");
}

function cruiseLogItem(time, title, note, tone = "neutral") {
  return `<article data-tone="${safeText(tone)}"><span>${safeText(time)}</span><strong>${safeText(title)}</strong><small>${safeText(note)}</small></article>`;
}

function renderCruiseLog(context = {}) {
  const list = $("#cruiseLogList");
  if (!list) return;
  const counts = state.dashboard?.counts || {};
  const riskCount = context.riskCount ?? ((counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length));
  const priorityCount = context.priorityCount ?? priorityItems().length;
  const launchCount = context.launchCount ?? contractLaunchItems().length;
  const queueCount = context.queueCount ?? (state.telegramStatus?.queueTotal ?? telegramQueueItems().length);
  const fileCount = context.fileCount ?? (state.fileSync?.fileCount || 0);
  const healthRows = state.downloadHealth || [];
  const healthOk = context.healthOk ?? healthRows.filter((item) => item.ok).length;
  const healthTotal = context.healthTotal ?? healthRows.length;
  const dashboardTime = context.dashboardTime || state.dashboard?.generatedAt || state.snapshotMeta?.updatedAt;
  const ageText = context.ageText || fmtAge(dashboardTime);
  const isFresh = context.isFresh ?? (dashboardTime && Date.now() - new Date(dashboardTime).getTime() < 10 * 60_000);
  const nextSeconds = state.nextRefreshAt ? Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000)) : 60;
  const stamp = state.lastRefreshAt ? new Date(state.lastRefreshAt).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }) : "--";
  const healthText = healthTotal ? `${healthOk}/${healthTotal}` : "等待";
  $("#cruiseLogSummary").textContent = state.refreshInFlight
    ? "正在写入本轮自动同步记录。"
    : `最近 ${stamp} 完成巡航，下一轮 ${nextSeconds} 秒后开始。`;
  const rows = [
    cruiseLogItem(stamp, `${state.dataMode || "连接中"}行情已刷新`, isFresh ? `数据 ${ageText}` : "等待新鲜快照", isFresh ? "good" : "warn"),
    cruiseLogItem(stamp, riskCount ? `风控拦截 ${riskCount} 项` : "风控检查通过", riskCount ? "风险优先，不追高" : "纪律正常", riskCount ? "warn" : "good"),
    cruiseLogItem(stamp, `候选队列 ${priorityCount} / 合约 ${launchCount}`, priorityCount ? "只允许观察和纸交易复核" : "等待下一轮信号", priorityCount ? "neutral" : "waiting"),
    cruiseLogItem(stamp, `分发链路 TG ${queueCount || 0} · 下载 ${healthText}`, `${fileCount || "--"} 文件同步`, healthTotal && healthOk === healthTotal ? "good" : "neutral"),
    cruiseLogItem(stamp, `缓存版本 v${APP_VERSION}`, `PWA 手机端一致 · ${nextSeconds}秒后刷新`, state.lastRefreshError ? "warn" : "good"),
  ];
  list.innerHTML = rows.join("");
}

function renderMetrics() {
  const counts = state.dashboard?.counts || {};
  const refreshedAt = new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  $("#generatedAt").textContent = fmtTime(state.dashboard?.generatedAt);
  $("#refreshedAt").textContent = refreshedAt;
  $("#topRefreshedAt").textContent = refreshedAt;
  $("#tickers").textContent = counts.tickers ?? "--";
  $("#entryCount").textContent = counts.entryWindow ?? "--";
  $("#earlyCount").textContent = counts.earlyEntryRadar ?? "--";
  $("#riskCount").textContent = (counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length);
  $("#skillOpportunities").textContent = `${(state.dashboard?.entryWindow || []).length + (state.dashboard?.earlyEntryRadar || []).length + (state.dashboard?.opportunities || []).length} 条`;
  $("#skillRisk").textContent = `${(counts.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length)} 条`;
  renderTradeDesk();
  renderPriority();
  renderSearchResults();
  renderWatchlist();
  renderSignalTrail();
  renderRiskRadar();
  renderBrief();
  renderSyncBoard();
  renderSources();
  renderExchangeApi();
  renderTelegramQueue();
  renderTradeExecutionLab();
  renderNavMeta();
  renderProGuard();
}

function renderTradeDesk() {
  const primary = priorityItems()[0] || contractLaunchItems()[0] || (state.dashboard?.entryWindow || [])[0];
  const riskCount = (state.dashboard?.counts?.delistRiskBlocked || 0) + ((state.dashboard?.overheated || []).length);
  const signalGate = state.gatePreflight?.signalTradeGate || {};
  const queue = [
    ...priorityItems().slice(0, 3),
    ...contractLaunchItems().slice(0, 3),
  ];
  const unique = [];
  const seen = new Set();
  for (const item of queue) {
    const ticker = String(item?.ticker || "").toUpperCase();
    if (!ticker || seen.has(ticker)) continue;
    seen.add(ticker);
    unique.push(item);
  }
  if (!primary) {
    setText("#deskMode", "观察模式");
    setText("#deskTicker", "等待同步");
    setText("#deskStage", "--");
    setText("#deskNote", "同步后显示当前最值得优先观察的币种和处理动作。");
    setText("#deskChange", "--");
    setText("#deskOi", "--");
    setText("#deskScore", "--");
    setText("#deskRisk", signalGate.signalActive ? "待确认" : "自动关闭");
    setText("#deskQueueMeta", "0 条");
    setHTML("#deskSignalRows", "<article><span>--</span><strong>等待数据</strong><small>自动同步中</small></article>");
    return;
  }
  const metric = tokenMetric(primary);
  const score = Math.round(signalScore(primary));
  const bucket = actionBucket(primary);
  setText("#deskMode", signalGate.signalActive ? "信号待确认" : (riskCount ? "先看风险" : "观察模式"));
  setText("#deskTicker", metric.ticker);
  setText("#deskStage", bucket);
  setText("#deskNote", nextAction(primary));
  setText("#deskChange", fmtPct(metric.change));
  setText("#deskOi", fmtPct(metric.oi));
  setText("#deskScore", String(score));
  setText("#deskRisk", signalGate.signalActive ? "待确认" : (riskCount ? `${riskCount} 风险` : "自动关闭"));
  setText("#deskQueueMeta", `${unique.length} 条`);
  setHTML("#deskSignalRows", unique.slice(0, 5).map((item) => {
    const row = tokenMetric(item);
    return `
      <article>
        <span>${row.ticker}</span>
        <strong>${actionBucket(item)}</strong>
        <small class="${scoreClass(row.change)}">24h ${fmtPct(row.change)} · OI ${fmtPct(row.oi)}</small>
      </article>
    `;
  }).join(""));
}

function renderSyncBoard() {
  const dashboardTime = state.dashboard?.generatedAt;
  const snapshotTime = state.snapshotMeta?.updatedAt || dashboardTime;
  const fileSyncTime = state.fileSync?.generatedAt;
  const queueCount = telegramQueueItems().length;
  const telegramAge = state.telegramStatus?.updatedAt ? fmtAge(state.telegramStatus.updatedAt) : "";
  $("#liveSource").textContent = state.dataMode || "连接中";
  $("#topSyncState").textContent = state.dataMode === "实时" ? "实时同步" : (state.dataMode || "连接中");
  $("#liveSourceNote").textContent = dashboardTime ? `行情 ${fmtAge(dashboardTime)}` : "等待 Michill 公开行情";
  $("#snapshotFreshness").textContent = fmtAge(snapshotTime);
  $("#snapshotMode").textContent = state.snapshotMeta?.mode ? `模式 ${state.snapshotMeta.mode}` : "实时优先，失败回快照";
  $("#fileSyncFreshness").textContent = fmtAge(fileSyncTime);
  $("#fileSyncMode").textContent = state.fileSync?.fileCount ? `${state.fileSync.fileCount} 个文件已登记` : "APP / 网页 / Telegram";
  $("#telegramSyncState").textContent = state.telegramStatus?.status === "error" ? "异常" : "运行中";
  $("#telegramSyncNote").textContent = telegramAge
    ? `${telegramAge} · ${state.telegramStatus?.queueTotal ?? queueCount} 条队列`
    : (queueCount ? `${queueCount} 条队列待推送/已同步` : "入场、合约、优先级自动推送");
  renderNavMeta();
  renderProGuard();
}

async function renderUpdateStatus() {
  $("#appVersion").textContent = `v${APP_VERSION}`;
  $("#pageMode").textContent = navigator.onLine ? "在线" : "离线";
  $("#topExecutionMode").textContent = "实盘关闭";
  if (!("caches" in window)) {
    $("#cacheStatus").textContent = "浏览器";
    $("#updateStatus").textContent = "当前浏览器不支持缓存自检，页面仍可正常实时刷新。";
    return;
  }
  try {
    const keys = await caches.keys();
    const current = keys.find((key) => key === `wukong-pwa-v${APP_VERSION}`);
    $("#cacheStatus").textContent = current ? "已更新" : "待刷新";
    $("#updateStatus").textContent = current
      ? `当前已使用 v${APP_VERSION} 缓存。`
      : "发现旧缓存，可刷新到最新版。";
  } catch {
    $("#cacheStatus").textContent = "等待";
    $("#updateStatus").textContent = "缓存状态等待浏览器同步。";
  }
}

async function forceAppUpdate() {
  const button = $("#forceUpdateButton");
  const original = button.textContent;
  button.textContent = "刷新中";
  try {
    if ("serviceWorker" in navigator) {
      const registrations = await navigator.serviceWorker.getRegistrations();
      await Promise.all(registrations.map((registration) => registration.update()));
    }
    if ("caches" in window) {
      const keys = await caches.keys();
      await Promise.all(keys.filter((key) => key.startsWith("wukong-pwa-")).map((key) => caches.delete(key)));
    }
    window.location.href = `./index.html?v=${APP_VERSION}&updated=${Date.now()}`;
  } catch {
    button.textContent = "重试";
    $("#updateStatus").textContent = "刷新失败，请稍后再试。";
    window.setTimeout(() => {
      button.textContent = original;
    }, 2400);
  }
}

function installContext() {
  const ua = navigator.userAgent || "";
  const standalone = window.matchMedia?.("(display-mode: standalone)")?.matches || window.navigator.standalone;
  const isIOS = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  const isAndroid = /Android/i.test(ua);
  if (standalone) {
    return {
      device: "已安装",
      platform: isIOS ? "iPhone/iPad" : (isAndroid ? "Android" : "PWA"),
      mode: "主屏幕",
      state: "已安装",
      note: `当前正在以 APP 模式运行，版本 v${APP_VERSION}。`,
      href: `./index.html?v=${APP_VERSION}`,
      action: "打开最新版",
    };
  }
  if (isIOS) {
    return {
      device: "iPhone/iPad",
      platform: "iOS",
      mode: "Safari/配置",
      state: "待安装",
      note: "推荐用 Safari 打开，安装 iPhone 配置文件或添加到主屏幕。",
      href: `./downloads/wukong-ios-install.mobileconfig?v=${APP_VERSION}`,
      action: "安装 iPhone",
    };
  }
  if (isAndroid) {
    return {
      device: "Android",
      platform: "Android",
      mode: "APK",
      state: "待安装",
      note: "推荐直接下载 Android APK 安装，安装后继续实时同步。",
      href: `./downloads/wukong-android-release.apk?v=${APP_VERSION}`,
      action: "下载 APK",
    };
  }
  return {
    device: "浏览器",
    platform: "桌面/网页",
    mode: "下载中心",
    state: "可分享",
    note: "当前是网页浏览器，可打开下载中心给 iPhone 或 Android 安装。",
    href: `./install.html?v=${APP_VERSION}`,
    action: "打开下载中心",
  };
}

function renderInstallAssistant() {
  const context = installContext();
  $("#installAssistDevice").textContent = context.device;
  $("#installAssistPlatform").textContent = context.platform;
  $("#installAssistMode").textContent = context.mode;
  $("#installAssistState").textContent = context.state;
  $("#installAssistNote").textContent = context.note;
  const action = $("#installAssistPrimary");
  action.href = context.href;
  action.textContent = context.action;
  if (context.mode === "APK") action.setAttribute("download", "");
  else action.removeAttribute("download");
}

function telegramQueueItems() {
  const dashboard = state.dashboard || {};
  const rows = [
    ...(dashboard.entryWindow || []).slice(0, 4).map((item) => ({ kind: "入场", item, tone: "good" })),
    ...(dashboard.oiAnomalyWatch || []).slice(0, 4).map((item) => ({ kind: "合约启动", item, tone: "watch" })),
    ...priorityItems().slice(0, 3).map((item) => ({ kind: "优先级", item, tone: "good" })),
    ...riskRadarItems().slice(0, 3).map(({ source, item }) => ({ kind: source || "风险", item, tone: "danger" })),
  ];
  const seen = new Set();
  return rows.filter((row) => {
    const ticker = String(row.item?.ticker || "").toUpperCase();
    const key = `${row.kind}:${ticker}`;
    if (!ticker || seen.has(key)) return false;
    seen.add(key);
    return true;
  }).slice(0, 12);
}

function renderTelegramQueue() {
  const rows = telegramQueueItems();
  $("#telegramQueueCount").textContent = rows.length ? `${rows.length} 条` : "等待";
  if (!rows.length) {
    $("#telegramQueueList").innerHTML = '<div class="empty compact">等待下一轮同步生成 Telegram 推送队列</div>';
    return;
  }
  $("#telegramQueueList").innerHTML = rows.map(({ kind, item, tone }) => {
    const metric = tokenMetric(item);
    const note = item.reason || item.why || item.opportunityStructure || item.primaryOpportunityLane || metric.structure;
    return `
      <article class="telegram-queue-row ${tone}">
        <span>${kind}</span>
        <div>
          <strong>${metric.ticker} · ${metric.stage}</strong>
          <small>${compactText(note, 72)}</small>
        </div>
        <div>
          <strong class="${scoreClass(metric.change)}">${fmtPct(metric.change)}</strong>
          <small>OI ${fmtPct(metric.oi)} · 分 ${metric.score}</small>
        </div>
      </article>
    `;
  }).join("");
}

function renderTelegramStatus() {
  const status = state.telegramStatus;
  if (!status) {
    $("#telegramReceipt").textContent = "等待 Telegram 推送回执。";
    $("#telegramReceiptMeta").textContent = "等待推送统计。";
    return;
  }
  const types = status.sentTypes?.length ? status.sentTypes.join(" / ") : "心跳";
  const label = status.status === "error" ? `异常：${status.error || "等待恢复"}` : `${types} · ${status.messageChunks || 0} 段消息`;
  const counts = status.queueCounts || {};
  $("#telegramReceipt").textContent =
    `最近回执 ${fmtAge(status.updatedAt)} · ${label} · 队列 ${status.queueTotal ?? "--"} 条`;
  $("#telegramReceiptMeta").textContent =
    `${status.mode || "push"} · ${status.chatIdMasked || "已绑定"} · 行情 ${fmtTime(status.marketGeneratedAt)}`;
  $("#telegramReceiptTotal").textContent = `${status.queueTotal ?? 0} 条`;
  $("#telegramReceiptEntry").textContent = counts.entry ?? "--";
  $("#telegramReceiptContract").textContent = counts.contractLaunch ?? "--";
  $("#telegramReceiptPriority").textContent = counts.priority ?? "--";
  $("#telegramReceiptRisk").textContent = counts.risk ?? "--";
  renderSyncBoard();
  renderNavMeta();
}

function renderPriority() {
  const rows = priorityItems();
  const candidate = rows[0];
  if (!candidate) {
    $("#priorityTicker").textContent = "暂无入场候选";
    $("#priorityNote").textContent = "当前先观察 Gate 行情和风险区变化。";
    $("#priorityMove").textContent = "--";
    $("#priorityListCount").textContent = "0";
    $("#priorityList").innerHTML = '<div class="empty">当前没有可优先观察的候选</div>';
    $("#actionPlanCount").textContent = "0";
    $("#actionPlanList").innerHTML = '<div class="empty">当前没有下一步行动</div>';
    return;
  }
  const metric = tokenMetric(candidate);
  $("#priorityTicker").textContent = `${metric.ticker} · ${metric.stage}`;
  $("#priorityNote").textContent = metric.structure;
  $("#priorityMove").textContent = `${fmtPct(metric.change)} / OI ${fmtPct(metric.oi)} / ${metric.score}`;
  $("#priorityListCount").textContent = `${rows.length} 个候选`;
  $("#priorityList").innerHTML = rows.slice(0, 5).map((item, index) => {
    const row = tokenMetric(item);
    return `
      <article class="priority-row">
        <div class="priority-rank">${index + 1}</div>
        <div>
          <strong>${row.ticker} · ${actionBucket(item)}</strong>
          <span>${row.structure}</span>
        </div>
        <div>
          <strong class="${scoreClass(row.change)}">${fmtPct(row.change)}</strong>
          <span>OI ${fmtPct(row.oi)} · 分 ${Math.round(signalScore(item))}</span>
        </div>
        <button class="watch-button ${isWatched(row.ticker) ? "is-active" : ""}" type="button" data-watch-toggle="${row.ticker}">
          ${isWatched(row.ticker) ? "已关注" : "关注"}
        </button>
      </article>
    `;
  }).join("");
  $("#actionPlanCount").textContent = `${Math.min(rows.length, 3)} 条`;
  $("#actionPlanList").innerHTML = rows.slice(0, 3).map((item, index) => {
    const row = tokenMetric(item);
    return `
      <article class="action-row">
        <div class="action-title">
          <span>${index + 1}</span>
          <strong>${row.ticker}</strong>
          <small>${actionBucket(item)}</small>
        </div>
        <p>${nextAction(item)}</p>
        <div class="action-meta">
          <span>24h ${fmtPct(row.change)}</span>
          <span>OI ${fmtPct(row.oi)}</span>
          <span>分 ${Math.round(signalScore(item))}</span>
        </div>
      </article>
    `;
  }).join("");
}

function renderXSocial() {
  const social = state.xSocial;
  if (!social) return;
  const summary = social.summary || {};
  const rows = social.topTickers || [];
  $("#xPosts").textContent = summary.posts ?? "--";
  $("#xTickers").textContent = summary.tickers ?? "--";
  $("#xTopTicker").textContent = summary.topTicker || "--";
  $("#xMode").textContent = social.mode === "x-api-v2" ? "实时API" : "快照";
  $("#xStatus").textContent = `${summary.message || "X 社媒热度已同步"} · ${fmtTime(social.updatedAt)}`;
    if (!rows.length) {
    $("#xList").innerHTML = '<div class="empty">当前没有 X 热度币种</div>';
    renderSources();
    return;
  }
  $("#xList").innerHTML = rows.slice(0, 8).map((item) => `
    <a class="x-row" href="${item.searchUrl}" target="_blank" rel="noopener noreferrer">
      <div>
        <strong>$${item.ticker}</strong>
        <span>${item.stage || "观察"} · ${item.note || "社媒热度"}</span>
      </div>
      <div>
        <strong>${item.posts}</strong>
        <span>帖子 · 24h ${fmtPct(item.change24h)}</span>
      </div>
    </a>
  `).join("");
  renderSources();
}

async function refreshXSocial() {
  if (LOCAL_FILE_MODE) {
    $("#xMode").textContent = "网页端";
    $("#xStatus").textContent = "请用下载链接打开以启用实时同步";
    return;
  }
  try {
    const response = await fetch(X_SOCIAL_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`X快照 HTTP ${response.status}`);
    state.xSocial = await response.json();
    renderXSocial();
  } catch (error) {
    $("#xMode").textContent = "等待";
    $("#xStatus").textContent = `X 同步等待中：${error.message}`;
  }
}

function renderAlpha() {
  const alpha = state.alpha;
  if (!alpha) return;
  const summary = alpha.summary || {};
  const rows = alpha.tokens || [];
  $("#alphaTokens").textContent = summary.tokens ?? "--";
  $("#alphaMapped").textContent = summary.mappedTickers ?? "--";
  $("#alphaCoverage").textContent = Number.isFinite(Number(summary.coveragePct)) ? `${Number(summary.coveragePct).toFixed(1)}%` : "--";
  $("#alphaTopTicker").textContent = summary.topTicker || "--";
  $("#alphaMode").textContent = alpha.mode === "live" ? "实时" : "快照";
  $("#alphaStatus").textContent = `Alpha CA ${summary.tokens ?? "--"} · DEX候选 ${summary.dexCandidates ?? "--"} · ${fmtTime(alpha.alphaFetchedAt || alpha.updatedAt)}`;
  if (!rows.length) {
    $("#alphaList").innerHTML = '<div class="empty">当前没有 Binance Alpha 映射候选</div>';
    renderSources();
    return;
  }
  $("#alphaList").innerHTML = rows.slice(0, 8).map((item) => `
    <article class="alpha-row">
      <div>
        <strong>${item.ticker}</strong>
        <span>${item.stage || "观察"} · ${item.note || "Alpha 映射观察"}</span>
      </div>
      <div>
        <strong>${item.alphaScore ?? "--"}</strong>
        <span>Alpha分 · ${item.identityStatus || "none"}</span>
      </div>
      <div class="hide-mobile">
        <strong>${fmtPct(item.change24h)}</strong>
        <span>24h · OI ${fmtPct(item.oi1h)}</span>
      </div>
    </article>
  `).join("");
  renderSources();
  renderTradeExecutionLab();
}

async function refreshAlpha() {
  if (LOCAL_FILE_MODE) {
    $("#alphaMode").textContent = "网页端";
    $("#alphaStatus").textContent = "请用下载链接打开以启用 Alpha 快照";
    return;
  }
  try {
    const response = await fetch(ALPHA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`Alpha快照 HTTP ${response.status}`);
    state.alpha = await response.json();
    renderAlpha();
  } catch (error) {
    $("#alphaMode").textContent = "等待";
    $("#alphaStatus").textContent = `Alpha 同步等待中：${error.message}`;
  }
}

function renderCountdown() {
  if (!state.nextRefreshAt) {
    setText("#nextSync", "30秒");
    setText("#topNextSync", "30秒");
    setWidth("#syncProgressBar", "10px");
    setWidth("#globalRefreshLine", "10px");
    setText("#autoUpdateGuard", "30秒");
    renderUpdateSla();
    return;
  }
  const seconds = Math.max(0, Math.ceil((state.nextRefreshAt - Date.now()) / 1000));
  const text = seconds > 0 ? `${seconds}秒` : "即将同步";
  const progress = Math.max(0, Math.min(100, 100 - (seconds / (REFRESH_MS / 1000)) * 100));
  setText("#nextSync", text);
  setText("#topNextSync", text);
  setWidth("#syncProgressBar", progress > 0 ? `${progress.toFixed(0)}%` : "10px");
  setWidth("#globalRefreshLine", progress > 0 ? `${progress.toFixed(0)}%` : "10px");
  setText("#autoUpdateGuard", text);
  renderUpdateSla();
}

function renderList() {
  const items = currentItems();
  $("#sectionTitle").textContent = sectionLabels[state.section];
  $("#sectionCount").textContent = `${items.length} 条`;
  if (!items.length) {
    $("#tokenList").innerHTML = '<div class="empty">当前没有可显示的数据</div>';
    return;
  }
  $("#tokenList").innerHTML = items.slice(0, 18).map((item, index) => {
    const metric = tokenMetric(item);
    return `
      <article class="token-row" style="animation-delay:${Math.min(index * 24, 180)}ms">
        <div class="ticker">${metric.ticker}</div>
        <div class="stage">
          <strong>${metric.stage}</strong>
          <span>${metric.structure}</span>
        </div>
        <div class="numbers">
          <strong class="${scoreClass(metric.change)}">24h ${fmtPct(metric.change)}</strong>
          <span>OI ${fmtPct(metric.oi)} · 分 ${metric.score}</span>
        </div>
      </article>
    `;
  }).join("");
}

function fmtBytes(bytes) {
  const number = Number(bytes);
  if (!Number.isFinite(number)) return "--";
  if (number > 1024 * 1024) return `${(number / 1024 / 1024).toFixed(1)}MB`;
  if (number > 1024) return `${(number / 1024).toFixed(1)}KB`;
  return `${number}B`;
}

function renderFileSync() {
  const sync = state.fileSync;
  if (!sync) return;
  setText("#fileSyncCount", `${sync.fileCount} 个文件`);
  setHTML("#fileSyncRoles", Object.entries(sync.roles || {})
    .map(([role, count]) => `<span>${role} ${count}</span>`)
    .join(""));
  setHTML("#fileSyncList", (sync.files || []).slice(0, 16).map((file) => `
    <div class="file-row">
      <strong>${safeText(file.path)}</strong>
      <span>${safeText(file.role)}</span>
      <span>${fmtBytes(file.bytes)}</span>
    </div>
  `).join(""));
  renderSyncBoard();
  renderNavMeta();
}

async function refreshFileSync() {
  if (LOCAL_FILE_MODE) {
    setText("#fileSyncCount", "网页端同步");
    setHTML("#fileSyncList", '<div class="empty">请用公网下载链接打开，文件清单会每 30 秒同步。</div>');
    renderNavMeta();
    return;
  }
  try {
    const response = await fetch("./wukong_file_sync.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.fileSync = await response.json();
    renderFileSync();
  } catch {
    setText("#fileSyncCount", "等待同步");
  }
}

async function refreshTelegramStatus() {
  if (LOCAL_FILE_MODE) {
    $("#telegramReceipt").textContent = "请用公网下载链接打开，Telegram 回执会自动同步。";
    return;
  }
  try {
    const response = await fetch(TELEGRAM_STATUS_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.telegramStatus = await response.json();
    renderTelegramStatus();
  } catch {
    $("#telegramReceipt").textContent = "Telegram 回执等待同步。";
  }
}

function renderDownloadHealth() {
  const rows = state.downloadHealth || [];
  const okCount = rows.filter((item) => item.ok).length;
  $("#downloadHealthStatus").textContent = rows.length ? `${okCount}/${rows.length} 在线` : "检查中";
  if (!rows.length) {
    $("#downloadHealthList").innerHTML = '<div class="empty compact">等待下载自检</div>';
    renderNavMeta();
    return;
  }
  $("#downloadHealthList").innerHTML = rows.map((item) => `
    <article class="download-health-row ${item.ok ? "good" : "danger"}">
      <span>${item.ok ? "在线" : "异常"}</span>
      <div>
        <strong>${item.label}</strong>
        <small>${item.kind} · ${item.status || "--"}</small>
      </div>
      <div>
        <strong>${fmtBytes(item.bytes)}</strong>
        <small>${item.modified ? fmtTime(item.modified) : item.error || "实时检查"}</small>
      </div>
    </article>
  `).join("");
  renderNavMeta();
}

async function checkDownloadAsset(item) {
  if (LOCAL_FILE_MODE) {
    return { ...item, ok: true, status: "公网链接", bytes: null, modified: null, error: "" };
  }
  try {
    const response = await fetch(item.url, { method: "HEAD", cache: "no-store" });
    const bytes = Number(response.headers.get("content-length"));
    return {
      ...item,
      ok: response.ok,
      status: `HTTP ${response.status}`,
      bytes: Number.isFinite(bytes) ? bytes : null,
      modified: response.headers.get("last-modified"),
    };
  } catch (error) {
    return { ...item, ok: false, status: "失败", bytes: null, modified: null, error: error.message };
  }
}

async function refreshDownloadHealth() {
  state.downloadHealth = await Promise.all(DOWNLOAD_CHECKS.map(checkDownloadAsset));
  renderDownloadHealth();
}

function renderGateMarkets() {
  $("#gateStatus").textContent = state.gateMarkets.length ? `已同步 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit", second: "2-digit" })}` : "等待数据";
  if (!state.gateMarkets.length) {
    $("#gateList").innerHTML = '<div class="empty">等待 Gate API 数据</div>';
    renderNavMeta();
    return;
  }
  $("#gateList").innerHTML = state.gateMarkets.map((item) => `
    <article class="gate-row">
      <div class="pair">${item.symbol.replace("_USDT", "")}</div>
      <div>
        <strong>${fmtPrice(item.spot?.last)}</strong>
        <span>现货价</span>
      </div>
      <div>
        <strong class="${scoreClass(item.spot?.change_percentage)}">${fmtPct(item.spot?.change_percentage)}</strong>
        <span>现货24h</span>
      </div>
      <div class="hide-mobile">
        <strong>${fmtPrice(item.futures?.mark_price || item.futures?.last)}</strong>
        <span>合约标记</span>
      </div>
      <div class="hide-mobile">
        <strong class="${scoreClass(item.futures?.funding_rate)}">${fmtFunding(item.futures?.funding_rate)}</strong>
        <span>资金费率</span>
      </div>
    </article>
  `).join("");
  renderTradeExecutionLab();
  renderNavMeta();
}

async function gateJSON(path) {
  const response = await fetch(`${GATE_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`Gate HTTP ${response.status}`);
  return response.json();
}

async function refreshGateMarkets() {
  $("#gateStatus").textContent = "同步中";
  if (LOCAL_FILE_MODE) {
    setText("#gateStatus", "网页端");
    setHTML("#gateList", '<div class="empty">请用公网下载链接打开，Gate 快照会每 30 秒同步。</div>');
    renderSources();
    return;
  }
  try {
    if (REMOTE_BROWSER_FETCH) {
      const rows = await Promise.all(GATE_PAIRS.map(async (symbol) => {
        const [spot, futures] = await Promise.all([
          gateJSON(`/spot/tickers?currency_pair=${symbol}`),
          gateJSON(`/futures/usdt/tickers?contract=${symbol}`),
        ]);
        return {
          symbol,
          spot: Array.isArray(spot) ? spot[0] : spot,
          futures: Array.isArray(futures) ? futures[0] : futures,
        };
      }));
      state.gateMarkets = rows;
      state.gateSnapshotTime = new Date().toISOString();
      renderGateMarkets();
      renderSources();
      return;
    }
    throw new Error("使用本地 Gate 快照");
  } catch (error) {
    try {
      const response = await fetch(GATE_SNAPSHOT_URL, { cache: "no-store" });
      if (!response.ok) throw new Error(`Gate快照 HTTP ${response.status}`);
      const snapshot = await response.json();
      state.gateMarkets = snapshot.markets || [];
      state.gateSnapshotTime = snapshot.generatedAt || null;
      renderGateMarkets();
      renderSources();
      setText("#gateStatus", `快照 ${fmtTime(snapshot.generatedAt)}`);
    } catch (snapshotError) {
      setText("#gateStatus", "Gate失败");
      setHTML("#gateList", `<div class="empty">Gate API 同步失败：${error.message} / ${snapshotError.message}</div>`);
      renderSources();
    }
  }
}

async function refreshExchangeMarkets() {
  setText("#exchangeApiStatus", "同步中");
  if (LOCAL_FILE_MODE) {
    setText("#exchangeApiStatus", "网页端");
    setHTML("#exchangeApiList", '<div class="empty compact">请用下载链接打开，Binance / OKX / Gate 快照会每 30 秒同步。</div>');
    return;
  }
  try {
    const response = await fetch(EXCHANGE_SNAPSHOT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`交易所快照 HTTP ${response.status}`);
    const snapshot = await response.json();
    state.exchangeMarkets = snapshot;
    state.exchangeSnapshotTime = snapshot.generatedAt || null;
    renderExchangeApi();
    renderSources();
  } catch (error) {
    setText("#exchangeApiStatus", "同步失败");
    setHTML("#exchangeApiList", `<div class="empty compact">交易所 API 快照失败：${safeText(error.message)}</div>`);
    renderSources();
  }
}

async function fetchDashboardSnapshot() {
  if (LOCAL_FILE_MODE) {
    throw new Error("本地文件模式不读取快照");
  }
  const response = await fetch(SNAPSHOT_URL, { cache: "no-store" });
  if (!response.ok) throw new Error(`快照 HTTP ${response.status}`);
  const snapshot = await response.json();
  const dashboard = snapshot.dashboard || snapshot;
  if (!dashboard || !dashboard.counts) throw new Error("快照缺少 dashboard");
  state.snapshotMeta = {
    mode: snapshot.mode || "snapshot",
    updatedAt: snapshot.updatedAt || dashboard.generatedAt,
  };
  state.report = snapshot.report || state.report;
  state.calendar = snapshot.calendar || state.calendar;
  renderReview();
  return dashboard;
}

async function refreshReviewData() {
  if (LOCAL_FILE_MODE) {
    setText("#reviewStatus", "请用公网下载链接打开复盘数据");
    return;
  }
  try {
    const response = await fetch(SNAPSHOT_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`快照 HTTP ${response.status}`);
    const snapshot = await response.json();
    state.report = snapshot.report || null;
    state.calendar = snapshot.calendar || null;
    renderReview();
  } catch {
    setText("#reviewStatus", "复盘数据等待同步");
  }
}

async function refresh() {
  if (state.refreshInFlight) {
    renderUpdateSla();
    return;
  }
  state.refreshInFlight = true;
  const button = $("#refreshButton");
  if (button) button.classList.add("is-spinning");
  setText("#syncState", "同步中");
  setText("#topSyncState", "同步中");
  renderUpdateSla();
  if (LOCAL_FILE_MODE) {
    state.dataMode = "网页端";
    state.lastRefreshAt = Date.now();
    state.nextRefreshAt = state.lastRefreshAt + REFRESH_MS;
    state.lastRefreshError = "";
    setText("#syncState", "网页端");
    setText("#topSyncState", "打开公网链接");
    setHTML("#tokenList", '<div class="empty">本地文件预览已启用版块操作；实时数据请用顶部下载链接或公网地址打开。</div>');
    renderCountdown();
    if (button) button.classList.remove("is-spinning");
    state.refreshInFlight = false;
    renderUpdateSla();
    return;
  }
  try {
    if (REMOTE_BROWSER_FETCH) {
      const response = await fetch(`${API_BASE}/api/summary/public-dashboard`, { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      state.dashboard = await response.json();
      state.dataMode = "实时";
      state.snapshotMeta = {
        mode: "live-api",
        updatedAt: new Date().toISOString(),
      };
      state.lastRefreshAt = Date.now();
      state.nextRefreshAt = state.lastRefreshAt + REFRESH_MS;
      state.lastRefreshError = "";
      renderMetrics();
      renderList();
      renderCountdown();
      setText("#syncState", "实时");
      setText("#topSyncState", "实时同步");
      return;
    }
    throw new Error("使用本地行情快照");
  } catch (error) {
    try {
      state.dashboard = await fetchDashboardSnapshot();
      state.dataMode = "快照";
      state.lastRefreshAt = Date.now();
      state.nextRefreshAt = state.lastRefreshAt + REFRESH_MS;
      state.lastRefreshError = "";
      renderMetrics();
      renderList();
      renderCountdown();
      setText("#syncState", "快照");
      setText("#topSyncState", "快照同步");
    } catch (snapshotError) {
      setText("#syncState", "失败");
      setText("#topSyncState", "同步失败");
      state.lastRefreshError = `${error.message} / ${snapshotError.message}`;
      setHTML("#tokenList", `<div class="empty">同步失败：${error.message} / ${snapshotError.message}</div>`);
      renderUpdateSla();
    }
  } finally {
    if (button) button.classList.remove("is-spinning");
    state.refreshInFlight = false;
    renderUpdateSla();
  }
}

async function refreshIfStale(reason) {
  if (Date.now() - state.lastRefreshAt > 10_000) {
    $("#syncState").textContent = reason;
    $("#topSyncState").textContent = reason;
    await refresh();
  }
}

function bindTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((item) => item.classList.remove("is-active"));
      tab.classList.add("is-active");
      state.section = tab.dataset.section;
      renderList();
    });
  });
}

function bindInstall() {
  window.addEventListener("beforeinstallprompt", (event) => {
    event.preventDefault();
    state.deferredPrompt = event;
    $("#installPanel").hidden = false;
  });
  $("#installButton").addEventListener("click", async () => {
    if (!state.deferredPrompt) return;
    state.deferredPrompt.prompt();
    await state.deferredPrompt.userChoice;
    state.deferredPrompt = null;
    $("#installPanel").hidden = true;
  });
}

function bindWatchlist() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-watch-toggle]");
    if (!button) return;
    toggleWatch(button.dataset.watchToggle);
  });
}

function bindTelegramCommands() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-command]");
    if (!button) return;
    copyTelegramCommand(button);
  });
}

function bindShareLinks() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-share-link]");
    if (!button) return;
    copyShareLink(button);
  });
}

function bindPaperOrders() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-paper-order]");
    if (!button) return;
    const ticker = String(button.dataset.paperOrder || "").toUpperCase();
    const item = contractLaunchItems().find((row) => String(row.ticker || "").toUpperCase() === ticker);
    renderPaperTradePlan(item);
    $("#paperTradeMode").textContent = "已模拟";
  });
}

function showTopSection(groupId, historyMode = "replace") {
  const shell = $(".section-gated");
  if (!shell) return;
  const fallbackId = "overviewGroup";
  const target = document.getElementById(groupId) || document.getElementById(fallbackId);
  if (!target) return;
  const activeGroupId = target.id;
  document.querySelectorAll(".section-gated > .module-group").forEach((section) => {
    const active = section.id === activeGroupId;
    section.classList.toggle("is-active", active);
    section.hidden = !active;
  });
  document.querySelectorAll(".top-section-map [data-group], .bottom-tabbar [data-group]").forEach((control) => {
    const controlledId = control.dataset.group || "";
    const active = controlledId === activeGroupId;
    control.classList.toggle("is-active", active);
    if (controlledId) control.setAttribute("aria-controls", controlledId);
    control.setAttribute("aria-pressed", active ? "true" : "false");
    if (active) control.setAttribute("aria-current", "true");
    else control.removeAttribute("aria-current");
  });
  shell.classList.add("has-open-section");
  const hint = $("#sectionGateHint");
  if (hint) hint.hidden = true;
  if (historyMode === "push") {
    if (window.location.hash !== `#${activeGroupId}`) {
      history.pushState({ wukongGroup: activeGroupId }, "", `#${activeGroupId}`);
    }
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (historyMode === "replace" || historyMode === true) {
    history.replaceState({ wukongGroup: activeGroupId }, "", `#${activeGroupId}`);
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  } else if (groupId !== activeGroupId && window.location.hash) {
    history.replaceState({ wukongGroup: activeGroupId }, "", `#${activeGroupId}`);
  }
}

function syncTopSectionFromHash() {
  const next = window.location.hash ? window.location.hash.slice(1) : "overviewGroup";
  showTopSection(next, false);
}

function bindTopSections() {
  document.querySelectorAll(".section-gated > .module-group").forEach((section) => {
    section.hidden = true;
    section.classList.remove("is-active");
  });
  const hint = $("#sectionGateHint");
  if (hint) hint.hidden = false;
  document.addEventListener("click", (event) => {
    const link = event.target.closest(".top-section-map [data-group], .bottom-tabbar [data-group]");
    if (!link) return;
    event.preventDefault();
    showTopSection(link.dataset.group, "push");
  });
  window.addEventListener("hashchange", syncTopSectionFromHash);
  window.addEventListener("popstate", syncTopSectionFromHash);
  const initial = window.location.hash ? window.location.hash.slice(1) : "overviewGroup";
  showTopSection(initial, false);
}

if (!LOCAL_FILE_MODE && "serviceWorker" in navigator) {
  navigator.serviceWorker.register(`./sw.js?v=${APP_VERSION}`);
}

startDynamicMarkupGuard();

$("#refreshButton").addEventListener("click", refresh);
$("#topRefreshButton").addEventListener("click", refresh);
$("#copyBrief").addEventListener("click", copyBrief);
$("#forceUpdateButton").addEventListener("click", forceAppUpdate);
$("#tokenSearch").addEventListener("input", renderSearchResults);
$("#iosInstallHelp").addEventListener("click", () => {
  $("#installPanel").hidden = false;
  $("#installPanel p").textContent = "iPhone 请用 Safari 打开本页，点分享按钮，再点“添加到主屏幕”。";
  window.scrollTo({ top: document.body.scrollHeight, behavior: "smooth" });
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    refreshIfStale("回到前台");
  }
});
window.addEventListener("online", () => refreshIfStale("网络恢复"));
window.addEventListener("online", renderUpdateStatus);
window.addEventListener("offline", renderUpdateStatus);
bindTabs();
bindInstall();
bindWatchlist();
bindTelegramCommands();
bindShareLinks();
bindPaperOrders();
bindTopSections();
updateTelegramShareLink();
renderTradeExecutionLab();
renderInstallAssistant();
renderWatchlist();
renderReview();
renderUpdateStatus();
  renderNavMeta();
  renderProGuard();
  refresh();
refreshFileSync();
refreshTelegramStatus();
refreshDownloadHealth();
refreshExchangeMarkets();
refreshGatePrivateStatus();
refreshGateTradePreflight();
refreshPaperTradingState();
refreshProfessionalSystem();
refreshEmaCross4h();
refreshGateMarkets();
refreshXSocial();
refreshAlpha();
refreshReviewData();
state.timer = window.setInterval(refresh, REFRESH_MS);
window.setInterval(refreshFileSync, REFRESH_MS);
window.setInterval(refreshTelegramStatus, REFRESH_MS);
window.setInterval(refreshDownloadHealth, REFRESH_MS);
window.setInterval(refreshExchangeMarkets, REFRESH_MS);
window.setInterval(refreshGatePrivateStatus, REFRESH_MS);
window.setInterval(refreshGateTradePreflight, REFRESH_MS);
window.setInterval(refreshPaperTradingState, REFRESH_MS);
window.setInterval(refreshProfessionalSystem, REFRESH_MS);
window.setInterval(refreshEmaCross4h, REFRESH_MS);
window.setInterval(refreshGateMarkets, REFRESH_MS);
window.setInterval(refreshXSocial, REFRESH_MS);
window.setInterval(refreshAlpha, REFRESH_MS);
window.setInterval(refreshReviewData, REFRESH_MS);
window.setInterval(renderUpdateStatus, REFRESH_MS);
state.countdownTimer = window.setInterval(renderCountdown, 1000);
