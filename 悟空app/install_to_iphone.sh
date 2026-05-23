#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! xcodebuild -version >/dev/null 2>&1; then
  echo "未检测到完整 Xcode。请先安装 Xcode，并运行：sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
  exit 2
fi

if ! command -v xcodegen >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    brew install xcodegen
  else
    echo "缺少 xcodegen，也没有 Homebrew。请先安装 XcodeGen。"
    exit 2
  fi
fi

TEAM_ARG=()
if [[ -n "${APPLE_TEAM_ID:-}" ]]; then
  TEAM_ARG=(DEVELOPMENT_TEAM="$APPLE_TEAM_ID")
fi

xcodegen generate

DEVICE_ID="${IPHONE_DEVICE_ID:-}"
if [[ -z "$DEVICE_ID" ]]; then
  DEVICE_ID="$(xcrun devicectl list devices 2>/dev/null | awk '/iPhone/ && /connected/ {print $1; exit}')"
fi
if [[ -z "$DEVICE_ID" ]] && command -v idevice_id >/dev/null 2>&1; then
  DEVICE_ID="$(idevice_id -l | head -n 1)"
fi

if [[ -z "$DEVICE_ID" ]]; then
  echo "没有检测到已连接并信任的 iPhone。镜像/投屏不等于开发安装连接；请用 USB 或 Xcode 无线调试配对，解锁手机并点“信任此电脑”。"
  xcrun devicectl list devices || true
  command -v idevice_id >/dev/null 2>&1 && idevice_id -l || true
  exit 3
fi

DERIVED_DATA="$ROOT/.xcode-derived"
rm -rf "$DERIVED_DATA"

xcodebuild \
  -project Wukong.xcodeproj \
  -scheme Wukong \
  -destination "platform=iOS,id=$DEVICE_ID" \
  -derivedDataPath "$DERIVED_DATA" \
  -allowProvisioningUpdates \
  "${TEAM_ARG[@]}" \
  build

APP_PATH="$DERIVED_DATA/Build/Products/Debug-iphoneos/悟空.app"
if [[ ! -d "$APP_PATH" ]]; then
  APP_PATH="$DERIVED_DATA/Build/Products/Debug-iphoneos/Wukong.app"
fi

if xcrun devicectl device install app --device "$DEVICE_ID" "$APP_PATH"; then
  echo "已安装到 iPhone：悟空"
  exit 0
fi

if command -v ios-deploy >/dev/null 2>&1; then
  ios-deploy --id "$DEVICE_ID" --bundle "$APP_PATH"
  echo "已通过 ios-deploy 安装到 iPhone：悟空"
  exit 0
fi

echo "构建成功，但安装失败。请在 Xcode 里打开 Wukong.xcodeproj，选择已配对 iPhone 后运行。"
exit 4
