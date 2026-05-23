#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

METHOD="${1:-app-store}"
case "$METHOD" in
  app-store|ad-hoc|development) ;;
  *)
    echo "用法：$0 [app-store|ad-hoc|development]"
    exit 64
    ;;
esac

if ! /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  echo "缺少完整 Xcode。请先安装 Xcode，并运行："
  echo "sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
  exit 2
fi

IDENTITIES="$(security find-identity -v -p codesigning 2>/dev/null || true)"
if [[ "$METHOD" == "development" ]]; then
  REQUIRED_IDENTITY="Apple Development"
else
  REQUIRED_IDENTITY="Apple Distribution"
fi
if ! echo "$IDENTITIES" | grep -q "$REQUIRED_IDENTITY"; then
  echo "没有找到 $REQUIRED_IDENTITY 签名证书。"
  echo "先在 Xcode 登录 Apple Developer 账号并创建/下载证书。"
  exit 3
fi

TEAM_ID="${APPLE_TEAM_ID:-}"
if [[ -z "$TEAM_ID" ]]; then
  echo "缺少 APPLE_TEAM_ID 环境变量。"
  echo "示例：APPLE_TEAM_ID=ABCDE12345 $0 $METHOD"
  exit 4
fi

if command -v xcodegen >/dev/null 2>&1; then
  xcodegen generate
fi

BUILD_ROOT="$ROOT/build/signed-ios"
ARCHIVE_PATH="$BUILD_ROOT/Wukong.xcarchive"
EXPORT_PATH="$BUILD_ROOT/export-$METHOD"
EXPORT_PLIST="$BUILD_ROOT/ExportOptions-$METHOD.plist"

rm -rf "$ARCHIVE_PATH" "$EXPORT_PATH"
mkdir -p "$EXPORT_PATH"

cat > "$EXPORT_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>destination</key>
	<string>export</string>
	<key>method</key>
	<string>$METHOD</string>
	<key>signingStyle</key>
	<string>automatic</string>
	<key>stripSwiftSymbols</key>
	<true/>
	<key>teamID</key>
	<string>$TEAM_ID</string>
</dict>
</plist>
PLIST

xcodebuild archive \
  -project Wukong.xcodeproj \
  -scheme Wukong \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath "$ARCHIVE_PATH" \
  DEVELOPMENT_TEAM="$TEAM_ID" \
  CODE_SIGN_STYLE=Automatic

xcodebuild -exportArchive \
  -archivePath "$ARCHIVE_PATH" \
  -exportPath "$EXPORT_PATH" \
  -exportOptionsPlist "$EXPORT_PLIST"

IPA="$(find "$EXPORT_PATH" -maxdepth 1 -name '*.ipa' | head -n 1)"
echo "签名完成：$IPA"
