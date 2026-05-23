#!/bin/zsh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "悟空 Apple 签名检查"
echo

echo "1. Xcode"
if /usr/bin/xcodebuild -version >/dev/null 2>&1; then
  /usr/bin/xcodebuild -version
else
  echo "FAIL: 当前没有完整 Xcode，或 xcode-select 没有指向 Xcode.app。"
  echo "FIX : sudo xcode-select -s /Applications/Xcode.app/Contents/Developer"
fi
echo

echo "2. Code signing identities"
IDS="$(security find-identity -v -p codesigning 2>/dev/null || true)"
echo "$IDS"
if ! echo "$IDS" | grep -q "Apple Distribution"; then
  echo "FAIL: 没有 Apple Distribution 签名证书。"
  echo "FIX : 在 Xcode 登录 Apple Developer 账号，创建或下载 Apple Distribution 证书。"
fi
if ! echo "$IDS" | grep -q "Apple Development"; then
  echo "WARN: 没有 Apple Development 签名证书，真机调试签名也不可用。"
fi
echo

echo "3. Provisioning profiles"
PROFILE_DIR="$HOME/Library/MobileDevice/Provisioning Profiles"
if [[ -d "$PROFILE_DIR" ]]; then
  COUNT="$(find "$PROFILE_DIR" -maxdepth 1 -type f -name '*.mobileprovision' | wc -l | tr -d ' ')"
  echo "$COUNT profiles found"
  find "$PROFILE_DIR" -maxdepth 1 -type f -name '*.mobileprovision' | sed -n '1,10p'
else
  echo "FAIL: 没有 provisioning profile 目录。"
fi
echo

echo "4. Project"
echo "Bundle ID: ai.wukong.app"
if [[ -d Wukong.xcodeproj ]]; then
  echo "Project: Wukong.xcodeproj OK"
else
  echo "FAIL: 缺少 Wukong.xcodeproj，可运行 xcodegen generate。"
fi
echo

echo "5. Next command after signing assets are ready"
echo "./scripts/build_signed_ios.sh app-store"
