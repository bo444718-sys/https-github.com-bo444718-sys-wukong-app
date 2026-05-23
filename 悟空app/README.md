# 悟空 / Wukong

一个原生 SwiftUI Apple 客户端，App 名称为“悟空”，复刻并重组 `https://michill.ai/#opportunities-panel` 的公开研究台。

## 已覆盖功能

- 总览：入场窗口、早发现雷达、确认/回踩候选、信号切换、OI 异动、风险区等核心计数。
- AI 复盘：读取公开报告、样本计数、共同特征、多维交叉组合与风险提示。
- 行情分区：入场窗口、早发现雷达、确认/回踩候选、信号轨迹、机会雷达、启动复盘、风险区。
- 币种搜索：调用 `/api/summary/ticker/:ticker` 查询历史轨迹。
- 我的关注：本机保存关注列表，不写回服务器。
- 详情页：展示价格、资金费率、OI 窗口、交易层闸门、入场/早发现信号、OI/量能/费率证据。
- AI 纸面日历摘要：读取 `/api/ai-trading-calendar`。
- 实时更新：启动后立即读取公开 API，并每 30 秒自动刷新一次，界面显示最近 App 刷新时间。
- 前台恢复同步：App 从后台回到前台时，如果数据超过 10 秒未刷新，会主动补一次同步。
- 技能中心：展示实时同步、机会扫描、风险过滤、Telegram 联动、本机关注和搜索轨迹等能力状态。

## 运行

```bash
cd "/Users/wangbo/Documents/New project/悟空app"
CLANG_MODULE_CACHE_PATH="$PWD/.build-cache/clang" \
SWIFTPM_HOME="$PWD/.build-cache/swiftpm" \
swift run --scratch-path "$PWD/.build"
```

当前机器没有完整 Xcode，只有 Command Line Tools；项目已通过 `swift build` 编译验证。安装 Xcode 后，可以直接打开这个 Swift Package，或把 `Sources/MichillAppleApp/main.swift` 放进 iOS/macOS SwiftUI App target 里继续做 Universal App，App 名称使用“悟空”。当前项目根目录为 `/Users/wangbo/Documents/New project/悟空app`。

## iPhone 下载地址

真正能让任意 iPhone 用户下载的地址必须由 Apple 创建：

- 悟空 App Store 下载地址：待 App Store Connect 审核通过后生成。
- 悟空 TestFlight 下载地址：待 Apple Developer 账号上传 build 后生成。

本地无法伪造这两个公开下载地址；它们必须绑定 Apple Developer 账号、Bundle ID、签名证书和审核流程。

## 数据源

- `https://michill.ai/api/summary/public-dashboard`
- `https://michill.ai/api/agent-team/public-report`
- `https://michill.ai/api/ai-trading-calendar`
- `https://michill.ai/api/summary/ticker/:ticker`

App 只展示公开研究信号，不构成投资建议，也不包含自动下单能力。

## Telegram 控制台

`telegram_wukong_bot.py` 可以把悟空内容发送到 Telegram，并让 Telegram 继续操作：

- 每 30 秒推送实时摘要。
- `/summary` 或 `/refresh` 立即发送摘要。
- `/section entryWindow` 查看入场窗口。
- `/section earlyEntryRadar` 查看早发现雷达。
- `/section opportunities` 查看确认/回踩候选。
- `/risk` 查看风险区。
- `/search APT` 搜索币种轨迹。
- `/watch add APT`、`/watch remove APT`、`/watch list` 管理关注。
- `/ask ...`、`/codex ...`、`/codel ...` 调用 OpenAI/Codex API 做只读分析。
- `wukong_latest_snapshot.json` 每次推送时同步写入，供现有 Hermes/Codex 网关读取最新悟空状态。
- `WUKONG_TELEGRAM_BRIDGE.md` 记录现有 Telegram/Codex 入口如何读取悟空快照。
- 每条悟空实时摘要会附带当前 iPhone 安装链接，链接来自 `/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt`。

现有机器人：

- 已验证本机现有 Telegram Bot 可用：`@verney_test_wukong6_bot`。
- 脚本会自动读取 `/Users/wangbo/.hermes/.env` 里的 `TELEGRAM_BOT_TOKEN`。
- 脚本会自动读取 `/Users/wangbo/.hermes/channel_directory.json` 里的现有 Telegram 对话。
- 因为现有机器人已经由 Hermes/Codex 网关接收消息，悟空应使用 `--push-only` 模式，只负责推送，不抢占 `getUpdates`。

可选配置：

```bash
cd "/Users/wangbo/Documents/New project/悟空app"
cp .env.telegram.example .env.telegram
```

如果只用现有机器人，可以不创建 `.env.telegram`。直接运行：

```bash
python3 telegram_wukong_bot.py --push-only
```

后台启动悟空每 30 秒推送：

```bash
python3 start_wukong_telegram.py
```

停止后台推送：

```bash
python3 stop_wukong_telegram.py
```

Telegram 里的继续操作由现有 Hermes/Codex 网关处理；你可以直接向 `@verney_test_wukong6_bot` 发送需求。

在 Telegram 里可以直接说：

```text
读取 /Users/wangbo/Documents/New project/悟空app/wukong_latest_snapshot.json，分析悟空最新机会和风险。
```

只发送一次摘要：

```bash
python3 telegram_wukong_bot.py --once
```

安全说明：不要把 `TELEGRAM_BOT_TOKEN`、`TELEGRAM_CHAT_ID`、`OPENAI_API_KEY` 写进源码或提交到 git。

## 自动恢复服务

当前已配置两个 macOS LaunchAgent：

- `ai.wukong.pwa`：每 5 分钟检查悟空 iPhone PWA 下载链接，断开时自动重建 Cloudflare tunnel，并把新链接发到 Telegram。
- `ai.wukong.telegram`：每 5 分钟检查悟空 Telegram 推送进程，断开时自动恢复。

运行副本放在：

- `/Users/wangbo/.hermes/wukong_pwa`
- `/Users/wangbo/.hermes/wukong_telegram`

健康检查：

```bash
python3 wukong_health.py
python3 wukong_health.py --send-telegram
```

报告会检查 PWA 下载链接、Cloudflare tunnel、Telegram 推送、LaunchAgent 状态和最新数据快照。

## 实时同步优化

悟空现在有三层同步：

- 原生 Apple App：启动同步、每 30 秒同步、回到前台补同步、手动下拉同步。
- 原生 Apple App 会自动读取 `/Users/wangbo/.hermes/wukong_telegram/wukong_latest_snapshot.json` 和 `/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt`，把 Telegram 快照、iPhone 安装链接和公开 API 数据同步到界面。
- 公开 API 暂时失败时，原生 Apple App 会用最新 Hermes 快照兜底显示。
- iPhone PWA：每 30 秒同步、回到前台补同步、网络恢复补同步、倒计时显示下次同步。
- Telegram：每 30 秒推送摘要、同步写入最新快照，并附带当前 iPhone 安装链接。

## 文件全量同步

`sync_wukong_files.py` 会扫描悟空目录核心文件，生成 `wukong_file_sync.json`，包含路径、用途、大小、修改时间、SHA-256 和文本预览。

同步目标：

- 原生 Apple App：新增“文件同步”页面，实时读取文件清单。
- 网页下载端 PWA：新增“文件同步”面板，实时显示文件角色和文件列表。
- Hermes 运行目录：`/Users/wangbo/.hermes/wukong_pwa/wukong_file_sync.json` 和 `/Users/wangbo/.hermes/wukong_telegram/wukong_file_sync.json`。

自动更新：

- PWA 巡检会先运行文件同步。
- Telegram 每 30 秒推送循环会先运行文件同步。
- 健康报告会显示文件数量和清单生成时间。

## Android / Apple 下载

同一个悟空下载端支持 Android 和 Apple：

- Android：网页端点击 `Android` 下载 APK，或直接访问 `/downloads/wukong-android-release.apk?v=121`。
- iPhone：网页端点击 `iPhone` 查看安装提示，在 Safari 里“添加到主屏幕”。

当前下载入口记录在 `ANDROID_IOS_DOWNLOAD.md`。
