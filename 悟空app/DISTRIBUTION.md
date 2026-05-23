# 悟空 / Wukong 正式分发方案

目标：让任何 Apple 用户可以下载“悟空”。

## 悟空下载地址

以下两个地址必须由 Apple Developer 账号创建，当前本地无法伪造：

- 悟空 App Store 下载地址：待 App Store Connect 审核通过后生成。
- 悟空 TestFlight 下载地址：待上传 iPhone build 并开启测试后生成。

## 推荐路线：App Store

适用范围：iPhone、iPad、Mac、Apple Silicon Mac。

必须条件：

- Apple Developer Program 账号。
- App Store Connect 中创建 App 记录。
- 唯一 Bundle ID，例如 `ai.wukong.scanner`。
- 使用 Xcode 对 iOS/macOS target 进行 Archive。
- 上传 build 到 App Store Connect。
- 填写隐私、年龄分级、截图、描述、审核备注。
- 提交 Apple App Review。

当前状态：

- SwiftUI 客户端源码已完成。
- macOS 本地 `.app` 已完成。
- 本机没有完整 Xcode，无法生成 App Store archive。
- 没有 Apple Developer 账号签名权限，无法上传到 App Store Connect。

## 备选路线：Mac 官网下载

适用范围：macOS 用户。

必须条件：

- Apple Developer Program 账号。
- Developer ID Application 证书。
- 对 `.app` 进行 Developer ID 签名。
- 打包为 `.dmg` 或 `.zip`。
- 使用 Apple notarization 服务公证。
- stapler 绑定公证票据。
- 上传到官网、GitHub Releases、Cloudflare Pages、S3 等下载地址。

当前本地 `.app` 只是 ad-hoc 签名，适合本机打开，不适合公开分发。

## App Store 元数据草案

App 名称：

悟空

副标题：

合约 OI 与早期信号研究台

分类：

Finance 或 Utilities

关键词：

crypto, Binance, OI, funding, futures, scanner, signal, dashboard, research, 加密货币, 合约, 资金费率, 复盘

简介：

悟空将 Binance 合约 OI、资金费率、成交量、价格位置、DEX 线索和社媒扩散整合成一个公开研究看板，帮助用户扫读高波动币种的早期信号、确认/回踩候选、信号轨迹、AI 复盘和风险提示。

免责声明：

本应用只展示公开市场数据、研究信号和复盘信息，不构成投资建议，不提供自动交易能力，也不保证数据实时性、完整性或准确性。加密资产和合约交易风险极高，请用户自行判断并控制风险。

审核备注：

Wukong is a read-only public research dashboard for crypto market signals. It does not execute trades, custody user funds, request exchange credentials, provide personalized financial advice, or offer in-app purchases. Data is loaded from public HTTPS endpoints on `michill.ai`. Watchlist data is stored locally on device only.

隐私草案：

- 不需要注册或登录。
- 不收集用户姓名、邮箱、手机号或金融账户。
- 不请求交易所 API key。
- 我的关注列表仅保存在本机。
- 应用会通过 HTTPS 请求 `michill.ai` 的公开行情与复盘接口。
- 如果服务器端保留访问日志，应在隐私政策中说明 IP、User-Agent、访问时间等常规日志用途。

## 需要你提供

- Apple Developer 账号访问权限，或你自己登录 Xcode / App Store Connect。
- App 的最终 Bundle ID。
- 开发者名称、支持邮箱、隐私政策 URL。
- 是否只发布 Mac，还是 iPhone/iPad/Mac 全平台。
- App 图标最终稿。
- App Store 截图。

## 我可以继续完成

- 创建正式 Xcode iOS/macOS Universal App 工程。
- 增加 App icon、Launch Screen、App Store 截图页面。
- 准备 App Store Connect 元数据。
- 在你登录 Apple Developer 账号后，协助 Archive、上传、提交审核。
- 如果只要 Mac 官网下载，协助 Developer ID 签名、公证、生成 `.dmg`。
