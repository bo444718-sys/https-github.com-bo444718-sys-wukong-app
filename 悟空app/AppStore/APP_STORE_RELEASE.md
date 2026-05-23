# 悟空 App Store 发布流程

当前项目已准备好 iOS 工程、图标、隐私清单、导出配置和商店文案。

## 当前机器状态

- 缺少完整 Xcode：当前 `xcodebuild` 指向 Command Line Tools。
- 缺少 Apple Distribution 签名证书：`security find-identity` 未发现有效证书。
- 因此当前机器不能直接生成 App Store `.ipa` 或提交审核。

## 上架前需要

1. 安装完整 Xcode。
2. 运行：

```bash
sudo xcode-select -s /Applications/Xcode.app/Contents/Developer
```

3. 在 Xcode 登录 Apple Developer 账号。
4. 在 App Store Connect 创建 App：
   - 名称：悟空
   - Bundle ID：`ai.wukong.app`
   - SKU：`wukong-ios-001`
5. 把 `AppStore/ExportOptions-AppStore.plist` 里的 `REPLACE_WITH_APPLE_TEAM_ID` 改为 Apple Team ID。

## 构建上传

```bash
./scripts/build_app_store.sh
```

脚本会执行：

- 重新生成 Xcode 工程
- Archive Release
- Export App Store Connect `.ipa`

如果配置了 `ASC_API_KEY_ID`、`ASC_API_ISSUER_ID` 和 `ASC_API_KEY_PATH`，脚本还会尝试上传到 App Store Connect。

## 单独签名

检查签名环境：

```bash
./scripts/apple_sign_check.sh
```

生成 Apple 签名 iOS 包：

```bash
APPLE_TEAM_ID=你的TeamID ./scripts/build_signed_ios.sh app-store
```

可选方法：

```bash
APPLE_TEAM_ID=你的TeamID ./scripts/build_signed_ios.sh ad-hoc
APPLE_TEAM_ID=你的TeamID ./scripts/build_signed_ios.sh development
```

## 官方入口

- App Store Connect: https://appstoreconnect.apple.com
- Apple Developer: https://developer.apple.com
