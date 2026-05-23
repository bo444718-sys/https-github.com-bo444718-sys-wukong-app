#!/usr/bin/env python3
"""Static server for the Wukong public download site."""

from __future__ import annotations

import mimetypes
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parent / "PWA"
PORT = 8088

mimetypes.add_type("application/x-apple-aspen-config", ".mobileconfig")
mimetypes.add_type("application/manifest+json", ".webmanifest")


class WukongHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mobileconfig": "application/x-apple-aspen-config",
        ".webmanifest": "application/manifest+json",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


def main() -> int:
    server = ThreadingHTTPServer(("0.0.0.0", PORT), WukongHandler)
    print(f"Wukong PWA server on http://0.0.0.0:{PORT}")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
