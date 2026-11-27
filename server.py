"""Loopback-only HTTP server for HookForge (Python standard library only)."""
from __future__ import annotations

import json
import mimetypes
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from hookforge_core import (
    MAX_EVENT_DEPTH,
    MAX_HOOKS,
    analyze_risk,
    export_document,
    simulate_hook,
    template_catalog,
    trigger_catalog,
    validate_document,
    validate_hook,
)

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
MAX_BODY = 65_536
STATIC_FILES = {"/": ("index.html", "text/html; charset=utf-8"), "/app.js": ("app.js", "text/javascript; charset=utf-8"), "/styles.css": ("styles.css", "text/css; charset=utf-8")}


class InputError(ValueError):
    pass


def _no_duplicate_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise InputError(f"Duplicate JSON key '{key}' is not allowed.")
        result[key] = value
    return result


def _check_depth(value: object, depth: int = 0) -> None:
    if depth > MAX_EVENT_DEPTH:
        raise InputError("JSON nesting is too deep.")
    if isinstance(value, dict):
        for child in value.values():
            _check_depth(child, depth + 1)
    elif isinstance(value, list):
        for child in value:
            _check_depth(child, depth + 1)


def parse_json_body(raw: bytes) -> object:
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InputError("Request body must be UTF-8.") from exc
    try:
        value = json.loads(text, object_pairs_hook=_no_duplicate_keys)
    except InputError:
        raise
    except (json.JSONDecodeError, RecursionError) as exc:
        raise InputError("Request body must be valid JSON.") from exc
    _check_depth(value)
    return value


class HookForgeHandler(BaseHTTPRequestHandler):
    server_version = "HookForge/1.0"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:
        # Avoid logging user prompts, commands, paths, or payloads.
        return

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Cross-Origin-Resource-Policy", "same-origin")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, status: int, value: object) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(body))
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._json(status, {"ok": False, "error": {"code": code, "message": message}})

    def _host_allowed(self) -> bool:
        host = self.headers.get("Host", "")
        try:
            parsed = urlsplit("//" + host)
            return (
                parsed.hostname in {"127.0.0.1", "localhost", "::1"}
                and parsed.username is None
                and (parsed.port is None or parsed.port == self.server.server_port)
            )
        except ValueError:
            return False

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._error(403, "host_rejected", "Use the loopback URL printed by run.py.")
            return
        path = urlsplit(self.path).path
        if path == "/api/health":
            self._json(200, {"ok": True, "service": "HookForge", "schema_version": "v1", "execution": False})
            return
        if path == "/api/meta":
            self._json(200, {"ok": True, "triggers": trigger_catalog(), "templates": template_catalog()})
            return
        if path not in STATIC_FILES:
            self._error(404, "not_found", "Resource not found.")
            return
        filename, content_type = STATIC_FILES[path]
        try:
            body = (FRONTEND / filename).read_bytes()
        except OSError:
            self._error(500, "static_unavailable", "Frontend asset is unavailable.")
            return
        self._headers(200, content_type, len(body))
        self.wfile.write(body)

    def _discard_small_body(self) -> None:
        """Drain a small rejected request so Windows does not reset the reply."""
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if 0 < length <= MAX_BODY:
            self.rfile.read(length)

    def _discard_available_body(self) -> None:
        """Drain bytes already sent so Windows does not reset a rejected reply."""
        previous_timeout = self.connection.gettimeout()
        try:
            self.connection.settimeout(0.05)
            self.rfile.read1(MAX_BODY)
        except (OSError, ValueError):
            pass
        finally:
            self.connection.settimeout(previous_timeout)

    def _discard_chunked_body(self) -> None:
        previous_timeout = self.connection.gettimeout()
        deadline = time.monotonic() + 0.5
        total = 0
        try:
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                self.connection.settimeout(remaining)
                line = self.rfile.readline(8192)
                if not line:
                    return
                try:
                    size = int(line.split(b";", 1)[0].strip(), 16)
                except ValueError:
                    return
                if size < 0 or total + size > MAX_BODY:
                    return
                if len(self.rfile.read(size)) != size or len(self.rfile.read(2)) != 2:
                    return
                total += size
                if size == 0:
                    return
        except OSError:
            return
        finally:
            self.connection.settimeout(previous_timeout)

    def do_POST(self) -> None:
        if not self._host_allowed():
            self._error(403, "host_rejected", "Use the loopback URL printed by run.py.")
            return
        path = urlsplit(self.path).path
        routes = {"/api/validate": "validate", "/api/document": "document", "/api/simulate": "simulate", "/api/risk": "risk", "/api/export": "export"}
        if path not in routes:
            self._discard_small_body()
            self._error(404, "not_found", "API route not found.")
            return
        if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/json":
            self._discard_small_body()
            self._error(415, "content_type", "Content-Type must be application/json.")
            return
        if self.headers.get("Transfer-Encoding"):
            self.close_connection = True
            self._discard_chunked_body()
            self._error(400, "chunked_unsupported", "Send a Content-Length request body.")
            return
        length_values = self.headers.get_all("Content-Length", [])
        if len(length_values) != 1:
            self.close_connection = True
            if len(set(length_values)) == 1:
                self._discard_small_body()
            else:
                self._discard_available_body()
            self._error(400, "invalid_input", "Exactly one Content-Length header is required.")
            return
        length_text = length_values[0].strip()
        if not length_text.isascii() or not length_text.isdigit():
            self.close_connection = True
            self._discard_available_body()
            self._error(400, "invalid_input", "A valid, non-empty Content-Length is required.")
            return
        length = int(length_text)
        if length <= 0:
            self._error(400, "invalid_input", "Request body cannot be empty.")
            return
        if length > MAX_BODY:
            self.close_connection = True
            self._discard_available_body()
            self._error(413, "body_too_large", f"Request body must be at most {MAX_BODY} bytes.")
            return
        try:
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise InputError("Incomplete request body.")
            payload = parse_json_body(raw)
            result = self._dispatch(routes[path], payload)
        except InputError as exc:
            self._error(400, "invalid_input", str(exc))
            return
        except (BrokenPipeError, ConnectionResetError):
            return
        except Exception:
            # Do not expose stack traces or submitted data.
            self._error(500, "internal_error", "HookForge could not process this request.")
            return
        self._json(200, result)

    def _dispatch(self, route: str, payload: object) -> dict[str, object]:
        if not isinstance(payload, dict):
            raise InputError("Request body must be a JSON object.")
        allowed = {"validate": {"hook"}, "document": {"document"}, "simulate": {"hook", "event"}, "risk": {"hook"}, "export": {"hook", "filename"}}
        unknown = set(payload) - allowed[route]
        if unknown:
            raise InputError(f"Unknown request field '{sorted(unknown)[0]}'.")
        if route == "document":
            return validate_document(payload.get("document"))
        hook = payload.get("hook")
        if route == "validate":
            return validate_hook(hook)
        if route == "risk":
            return analyze_risk(hook)
        if route == "simulate":
            return simulate_hook(hook, payload.get("event"))
        filename = payload.get("filename")
        if filename is not None and (not isinstance(filename, str) or len(filename) > 200):
            raise InputError("Filename must be a string of at most 200 characters.")
        if isinstance(hook, dict) and isinstance(hook.get("action"), dict):
            hooks = [hook]
            if len(hooks) > MAX_HOOKS:
                raise InputError("Too many hooks.")
        return export_document(hook, filename)


class HookForgeServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def create_server(host: str = "127.0.0.1", port: int = 8765) -> HookForgeServer:
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("HookForge may bind only to a loopback address.")
    if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("Port must be an integer from 1 to 65535.")
    server_class = HookForgeServer
    if host == "::1":
        class IPv6HookForgeServer(HookForgeServer):
            address_family = __import__("socket").AF_INET6
        server_class = IPv6HookForgeServer
    return server_class((host, port), HookForgeHandler)
