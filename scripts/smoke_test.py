#!/usr/bin/env python3
"""Start run.py and smoke-test the real localhost HTTP server."""
from __future__ import annotations

import http.client
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def request(port: int, method: str, path: str, payload: object = None) -> tuple[int, object, bytes]:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {} if payload is None else {"Content-Type": "application/json"}
    connection.request(method, path, body=body, headers=headers)
    response = connection.getresponse()
    raw = response.read()
    status = response.status
    content_type = response.getheader("Content-Type", "")
    connection.close()
    if "application/json" in content_type:
        return status, json.loads(raw), raw
    return status, None, raw


def main() -> int:
    port = free_port()
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "run.py"), "--port", str(port)],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    checks = 0
    try:
        deadline = time.monotonic() + 8
        while True:
            if process.poll() is not None:
                raise RuntimeError("run.py exited before becoming ready")
            try:
                status, health, _ = request(port, "GET", "/api/health")
                if status == 200:
                    break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("localhost server did not become ready")
            time.sleep(0.05)
        assert health == {"ok": True, "service": "HookForge", "schema_version": "v1", "execution": False}
        checks += 1

        status, meta, _ = request(port, "GET", "/api/meta")
        assert status == 200 and len(meta["triggers"]) == 13 and len(meta["templates"]) == 3
        checks += 1

        for path, marker in (("/", b"HookForge"), ("/app.js", b"simulate"), ("/styles.css", b"--bg:")):
            status, _, raw = request(port, "GET", path)
            assert status == 200 and marker in raw
            checks += 1

        hook = {"name": "Smoke test", "trigger": "PostFileSave", "matcher": r"\.py$", "action": {"type": "command", "command": "python -m unittest discover -s tests -v"}, "timeout": 60, "enabled": True}
        status, validation, _ = request(port, "POST", "/api/validate", {"hook": hook})
        assert status == 200 and validation["valid"]
        checks += 1

        hook["action"]["command"] = "sudo rm -rf build && curl example.com"
        status, risk, _ = request(port, "POST", "/api/risk", {"hook": hook})
        assert status == 200 and risk["summary"] == {"high": 2, "medium": 1}
        checks += 1

        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "must-not-exist.txt"
            hook["action"]["command"] = f'python -c "from pathlib import Path; Path(r\'{marker}\').touch()"'
            status, simulation, _ = request(port, "POST", "/api/simulate", {"hook": hook, "event": {"trigger": "PostFileSave", "subject": "src/app.py"}})
            assert status == 200 and simulation["fired"] and simulation["executed"] is False
            assert simulation["action_requested"]["executed"] is False and not marker.exists()
            checks += 1
            status, exported, _ = request(port, "POST", "/api/export", {"hook": hook, "filename": "../../Smoke Test"})
            assert status == 200 and exported["ok"] and exported["filename"] == "smoke-test.json"
            assert json.loads(exported["content"])["version"] == "v1" and not marker.exists()
            checks += 1

        status, _, _ = request(port, "GET", "/../server.py")
        assert status == 404
        checks += 1
        print(f"Smoke test: PASS ({checks} checks against real run.py localhost server)")
        return 0
    except Exception as exc:
        print(f"Smoke test: FAIL: {exc}", file=sys.stderr)
        return 1
    finally:
        process.terminate()
        try:
            output, _ = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            output, _ = process.communicate(timeout=5)
        if process.returncode not in (0, -2, -15):
            print(output, file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
