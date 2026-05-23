#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  echo "缺少完整 Xcode。请先安装 Xcode，并运行："
  echo "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
  exit 2
fi

if ! security find-identity -v -p codesigning | grep -q "Apple Distribution"; then
  echo "没有找到 Apple Distribution 签名证书。请先在 Xcode 登录 Apple Developer 账号并创建证书。"
  exit 3
fi

if command -v xcodegen >/dev/null 2>&1; then
  xcodegen generate
fi

ARCHIVE_PATH="$ROOT/build/AppStore/Wukong.xcarchive"
EXPORT_PATH="$ROOT/build/AppStore/export"

rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
mkdir -p "$EXPORT_PATH"

xcodebuild archive \
  -project Wukong.xcodeproj \
  -scheme Wukong \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath "$ARCHIVE_PATH"

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$ROOT/AppStore/ExportOptions-AppStore.plist"

IPA="$(find "$EXPORT_PATH" -name '*.ipa' -maxdepth 1 | head -n 1)"
echo "已生成：$IPA"

if [[ -n "${ASC_API_KEY_ID:-}" && -n "${ASC_API_ISSUER_ID:-}" && -n "${ASC_API_KEY_PATH:-}" ]]; then
  xcrun altool --upload-app \
    --type ios \
    --file "$IPA" \
    --apiKey "$ASC_API_KEY_ID" \
    --apiIssuer "$ASC_API_ISSUER_ID"
  echo "已上传到 App Store Connect。"
else
  echo "未配置 App Store Connect API Key，已跳过上传。"
fi
