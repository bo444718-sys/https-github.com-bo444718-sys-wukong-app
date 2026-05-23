# 悟空 Android / Apple 下载使用

当前可直接使用：

- Apple / iPhone：打开 PWA 链接后，在 Safari 里“添加到主屏幕”。
- Android：可安装 APK，或打开同一个 PWA 链接后在 Chrome 里“安装应用”。

当前安装中心：

https://stays-luxury-location-firm.trycloudflare.com/install.html?v=121

iPhone / Apple 安装：

https://stays-luxury-location-firm.trycloudflare.com/install.html?v=121

Android APK 直接下载：

https://stays-luxury-location-firm.trycloudflare.com/downloads/wukong-android-release.apk?v=121

Android APK 构建：

```bash
cd "/Users/wangbo/Documents/New project/悟空app"
npm run android:debug
```

构建产物：

```text
android/app/build/outputs/apk/debug/app-debug.apk
android/app/build/outputs/apk/release/app-release.apk
PWA/downloads/wukong-android-release.apk
```

Apple 原生安装：

- iPhone 真机原生安装仍需要完整 Xcode、Apple ID 签名和设备信任。
- 当前已经准备好 SwiftUI 原生工程和 Capacitor iOS 配置；安装 Xcode 后可继续生成 TestFlight/App Store 包。

同步机制：

- Android/iOS/PWA 都共用 `PWA/` 前端。
- `sync_wukong_files.py` 会同步悟空文件清单到 App 与网页下载端。
- PWA、Telegram 和原生 App 继续每分钟读取实时数据与快照。
- 下载链接统一带 `v=121`，避免手机或浏览器拿到旧缓存。
