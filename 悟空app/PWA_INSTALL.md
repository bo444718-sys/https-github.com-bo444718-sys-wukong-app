# 悟空 iPhone 临时安装链接

当前可用链接：

https://conferences-engines-cope-foundation.trycloudflare.com/install.html?v=121

iPhone 安装方式：

1. 在 iPhone Safari 打开上面的链接。
2. 点击分享按钮。
3. 选择“添加到主屏幕”。
4. 名称填写“悟空”。
5. 从主屏幕打开“悟空”。

说明：

- 这是 PWA 版本，可以像 App 一样从主屏幕打开。
- 数据每 30 秒从 Michill、Gate、本地同步快照和 Telegram 状态更新。
- 当前安装链接带 `v=121`，用于强制刷新手机端缓存和安装配置。
- 这个链接由 Cloudflare Quick Tunnel 提供，适合当前装机测试；终端里的 tunnel 进程停止后链接会失效。
- App Store/TestFlight 真正下载地址仍需要完整 Xcode、Apple Developer 签名和 Apple 审核流程。

重新生成临时安装链接：

```bash
cd "/Users/wangbo/Documents/New project/悟空app"
python3 start_wukong_pwa.py
```

停止 PWA 服务：

```bash
python3 stop_wukong_pwa.py
```

最新链接会写入 `wukong_pwa_url.txt`，并自动发送到现有 Telegram。

开机自动恢复：

```bash
mkdir -p ~/.hermes/wukong_pwa
rsync -a --delete PWA/ ~/.hermes/wukong_pwa/PWA/
cp start_wukong_pwa.py stop_wukong_pwa.py ~/.hermes/wukong_pwa/
cp ai.wukong.pwa.plist ~/Library/LaunchAgents/ai.wukong.pwa.plist
launchctl unload ~/Library/LaunchAgents/ai.wukong.pwa.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/ai.wukong.pwa.plist
```
