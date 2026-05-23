#!/usr/bin/env python3
"""Generate Wukong Apple and Android download QR codes."""

from __future__ import annotations

from pathlib import Path

import qrcode


ROOT = Path(__file__).resolve().parent
PWA = ROOT / "PWA"
QR_DIR = PWA / "qr"
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


def write_qr(value: str, path: Path) -> None:
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=3,
    )
    qr.add_data(value)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#070b12", back_color="#eef9ff")
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main() -> int:
    pwa_url = current_pwa_url()
    ios_url = f"{pwa_url}/install.html?v=121"
    android_url = f"{pwa_url}/downloads/wukong-android-release.apk?v=121"
    write_qr(ios_url, QR_DIR / "wukong-ios-qr.png")
    write_qr(android_url, QR_DIR / "wukong-android-qr.png")
    (QR_DIR / "download-links.txt").write_text(
        f"Apple/iPhone: {ios_url}\nAndroid APK: {android_url}\nInstall center: {ios_url}\n",
        encoding="utf-8",
    )
    print(f"Apple QR: {ios_url}")
    print(f"Android QR: {android_url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
