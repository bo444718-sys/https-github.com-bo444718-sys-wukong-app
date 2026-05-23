# 悟空 iPhone 真机安装

当前机器只安装了 Command Line Tools，没有完整 Xcode，因此不能直接把 iOS App 签名并安装到 iPhone。

已安装辅助工具：

- `xcodegen`：生成 Xcode 工程。
- `ios-deploy`：备用真机安装通道。
- `libimobiledevice`：备用设备识别通道。

当前检测结果：镜像/投屏可用，但命令行没有检测到可安装的 iPhone 设备。iOS 真机安装需要 USB 信任连接，或 Xcode 已完成无线调试配对。

已准备好的装机入口：

```bash
cd "/Users/wangbo/Documents/New project/悟空app"
./install_to_iphone.sh
```

运行条件：

- 安装完整 Xcode。
- 执行 `sudo xcode-select -s /Applications/Xcode.app/Contents/Developer`。
- iPhone 解锁并信任这台 Mac。
- Xcode 已登录 Apple ID，或设置 `APPLE_TEAM_ID`。

可选环境变量：

```bash
export APPLE_TEAM_ID=你的Apple开发团队ID
export IPHONE_DEVICE_ID=你的iPhone设备ID
./install_to_iphone.sh
```

脚本会自动：

- 用 `project.yml` 生成 `Wukong.xcodeproj`。
- 自动签名。
- 构建 iOS App。
- 通过 `devicectl` 安装到已连接 iPhone，失败时尝试 `ios-deploy`。
