#!/usr/bin/env python3
"""Run the local HookForge studio."""
from __future__ import annotations

import argparse
import sys
import webbrowser

from server import create_server


def main() -> int:
    parser = argparse.ArgumentParser(description="HookForge: a safe, local Kiro IDE 1.x hook builder")
    parser.add_argument("--host", default="127.0.0.1", choices=["127.0.0.1", "localhost", "::1"], help="loopback address only")
    parser.add_argument("--port", type=int, default=8765, help="port (default: 8765)")
    parser.add_argument("--open", action="store_true", help="open the studio in a browser")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    try:
        server = create_server(args.host, args.port)
    except (OSError, ValueError) as exc:
        print(f"HookForge could not start: {exc}", file=sys.stderr)
        return 1
    display_host = "[::1]" if args.host == "::1" else args.host
    url = f"http://{display_host}:{server.server_address[1]}/"
    print(f"HookForge is running at {url}")
    print("Loopback only. Submitted commands are never executed. Press Ctrl+C to stop.")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nHookForge stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
