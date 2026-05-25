#!/usr/bin/env python3
"""Generate a downloadable iPhone Web Clip profile for Wukong."""

from __future__ import annotations

import base64
import plistlib
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PWA = ROOT / "PWA"
PROFILE_PATH = PWA / "downloads" / "wukong-ios-install.mobileconfig"
PWA_URL_PATHS = [
    Path("/Users/wangbo/.hermes/wukong_pwa/wukong_pwa_url.txt"),
    ROOT / "wukong_pwa_url.txt",
]


def current_pwa_url() -> str:
    for path in PWA_URL_PATHS:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value.startswith(("https://", "http://")):
            return value.rstrip("/")
    raise SystemExit("Missing current Wukong PWA URL.")


def main() -> int:
    app_url = f"{current_pwa_url()}/index.html?v=122"
    icon = (PWA / "icons" / "wukong-180.png").read_bytes()
    webclip_uuid = str(uuid.uuid4()).upper()
    profile_uuid = str(uuid.uuid4()).upper()
    payload = {
        "PayloadContent": [
            {
                "FullScreen": True,
                "Icon": icon,
                "IsRemovable": True,
                "Label": "悟空",
                "PayloadDescription": "把悟空安装到 iPhone 主屏幕。",
                "PayloadDisplayName": "悟空",
                "PayloadIdentifier": "ai.wukong.webclip",
                "PayloadType": "com.apple.webClip.managed",
                "PayloadUUID": webclip_uuid,
                "PayloadVersion": 1,
                "Precomposed": True,
                "URL": app_url,
            }
        ],
        "PayloadDescription": "安装悟空到 iPhone 主屏幕。",
        "PayloadDisplayName": "悟空 iPhone 安装",
        "PayloadIdentifier": "ai.wukong.install",
        "PayloadOrganization": "悟空",
        "PayloadRemovalDisallowed": False,
        "PayloadType": "Configuration",
        "PayloadUUID": profile_uuid,
        "PayloadVersion": 1,
    }
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with PROFILE_PATH.open("wb") as handle:
        plistlib.dump(payload, handle, sort_keys=False)
    encoded = base64.b64encode(PROFILE_PATH.read_bytes()).decode("ascii")
    (PROFILE_PATH.with_suffix(".mobileconfig.b64.txt")).write_text(encoded, encoding="utf-8")
    print(f"iPhone profile: {PROFILE_PATH}")
    print(f"WebClip URL: {app_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
