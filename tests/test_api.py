"""HTTP contract and boundary tests against an ephemeral loopback server."""
from __future__ import annotations

import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from server import HookForgeServer, HookForgeHandler, parse_json_body, InputError


def valid_hook():
    return {"name": "Test runner", "trigger": "PostFileSave", "matcher": r"\.py$", "action": {"type": "command", "command": "python -m unittest discover -s tests -v"}, "timeout": 60, "enabled": True}


class ServerCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HookForgeServer(("127.0.0.1", 0), HookForgeHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.port = cls.server.server_address[1]

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        if isinstance(body, (dict, list)):
            body = json.dumps(body).encode("utf-8")
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = (response.status, dict(response.getheaders()), raw)
        connection.close()
        return result

    def post(self, path, payload, content_type="application/json"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode("utf-8")
        return self.request("POST", path, body, {"Content-Type": content_type, "Content-Length": str(len(body))})


class StaticAndMetaTests(ServerCase):
    def test_index_and_assets(self):
        status, headers, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        self.assertIn(b"HookForge", body)
        for path, marker in (("/app.js", b"simulate"), ("/styles.css", b"--bg:")):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertIn(marker, body)

    def test_security_headers(self):
        _, headers, _ = self.request("GET", "/")
        csp = headers["Content-Security-Policy"]
        self.assertIn("default-src 'self'", csp)
        self.assertIn("connect-src 'self'", csp)
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Frame-Options"], "DENY")

    def test_meta_lists_triggers_and_templates(self):
        status, _, raw = self.request("GET", "/api/meta")
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(len(data["triggers"]), 13)
        self.assertEqual(len(data["templates"]), 3)

    def test_health(self):
        status, _, raw = self.request("GET", "/api/health")
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw)["execution"])

    def test_unknown_and_traversal_paths_rejected(self):
        for path in ("/missing", "/../server.py", "/%2e%2e/server.py", "/api/unknown"):
            with self.subTest(path=path):
                self.assertEqual(self.request("GET", path)[0], 404)

    def test_query_string_still_serves_known_static_path(self):
        self.assertEqual(self.request("GET", "/?cache=1")[0], 200)

    def test_post_to_static_and_get_to_api_post_route(self):
        self.assertEqual(self.post("/", {"hook": valid_hook()})[0], 404)
        self.assertEqual(self.request("GET", "/api/validate")[0], 404)

    def test_wrong_host_port_rejected(self):
        status, _, raw = self.request("GET", "/", headers={"Host": f"127.0.0.1:{self.port + 1}"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "host_rejected")

    def test_foreign_host_rejected(self):
        status, _, raw = self.request("GET", "/", headers={"Host": "evil.example"})
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(raw)["error"]["code"], "host_rejected")


class ValidationApiTests(ServerCase):
    def test_valid_hook(self):
        status, _, raw = self.post("/api/validate", {"hook": valid_hook()})
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["valid"])

    def test_invalid_hook_is_200_with_diagnostics(self):
        status, _, raw = self.post("/api/validate", {"hook": {"name": "", "trigger": "wrong", "action": {"type": "command"}}})
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertFalse(data["valid"])
        self.assertGreaterEqual(len(data["issues"]), 3)

    def test_document_validation_prefixes_paths(self):
        status, _, raw = self.post("/api/document", {"document": {"version": "v1", "hooks": [valid_hook(), {"name": ""}]}})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertFalse(data["valid"])
        self.assertTrue(any(issue["path"].startswith("$.hooks[1].") for issue in data["issues"]))

    def test_non_object_payload_rejected(self):
        self.assertEqual(self.post("/api/validate", [])[0], 400)

    def test_unknown_request_field_rejected(self):
        status, _, raw = self.post("/api/validate", {"hook": valid_hook(), "command": "true"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_input")

    def test_missing_hook_rejected_as_invalid_hook(self):
        status, _, raw = self.post("/api/validate", {})
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(raw)["valid"])


class InputBoundaryTests(ServerCase):
    def test_invalid_json(self):
        self.assertEqual(self.post("/api/validate", b"{")[0], 400)

    def test_invalid_utf8(self):
        self.assertEqual(self.post("/api/validate", b"\xff")[0], 400)

    def test_duplicate_keys_rejected(self):
        raw = b'{"hook":{},"hook":{}}'
        self.assertEqual(self.post("/api/validate", raw)[0], 400)

    def test_wrong_content_type(self):
        self.assertEqual(self.post("/api/validate", {"hook": valid_hook()}, "text/plain")[0], 415)

    def test_content_type_with_charset_accepted(self):
        self.assertEqual(self.post("/api/validate", {"hook": valid_hook()}, "application/json; charset=utf-8")[0], 200)

    def test_empty_body(self):
        status, _, _ = self.request("POST", "/api/validate", b"", {"Content-Type": "application/json", "Content-Length": "0"})
        self.assertEqual(status, 400)

    def raw_post(self, headers):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.putrequest("POST", "/api/validate", skip_accept_encoding=True)
        for name, value in headers:
            connection.putheader(name, value)
        connection.endheaders(b"{}")
        response = connection.getresponse()
        result = (response.status, dict(response.getheaders()), response.read())
        connection.close()
        return result

    def test_duplicate_content_length_rejected(self):
        status, _, raw = self.raw_post((("Content-Type", "application/json"), ("Content-Length", "2"), ("Content-Length", "2")))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_input")

    def test_conflicting_content_length_rejected(self):
        status, _, raw = self.raw_post((("Content-Type", "application/json"), ("Content-Length", "2"), ("Content-Length", "3")))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_input")

    def test_signed_content_length_rejected(self):
        status, _, raw = self.raw_post((("Content-Type", "application/json"), ("Content-Length", "+2")))
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "invalid_input")

    def test_oversized_body_rejected_before_read(self):
        status, _, raw = self.request("POST", "/api/validate", b"{}", {"Content-Type": "application/json", "Content-Length": "65537"})
        self.assertEqual(status, 413)
        self.assertEqual(json.loads(raw)["error"]["code"], "body_too_large")

    def test_chunked_body_rejected(self):
        status, _, raw = self.request("POST", "/api/validate", b"{}", {"Content-Type": "application/json", "Transfer-Encoding": "chunked"})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["error"]["code"], "chunked_unsupported")

    def test_deep_nesting_rejected(self):
        with self.assertRaises(InputError):
            parse_json_body(b"[" * 20 + b"0" + b"]" * 20)

    def test_filename_boundary(self):
        self.assertEqual(self.post("/api/export", {"hook": valid_hook(), "filename": "x" * 201})[0], 400)
        self.assertEqual(self.post("/api/export", {"hook": valid_hook(), "filename": 3})[0], 400)


class RiskSimulationExportApiTests(ServerCase):
    def test_risk_warnings(self):
        hook = valid_hook()
        hook["action"]["command"] = "sudo rm -rf build && curl example.com"
        status, _, raw = self.post("/api/risk", {"hook": hook})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["summary"], {"high": 2, "medium": 1})

    def test_simulation_match_and_mismatch(self):
        for subject, fired in (("src/app.py", True), ("README.md", False)):
            status, _, raw = self.post("/api/simulate", {"hook": valid_hook(), "event": {"trigger": "PostFileSave", "subject": subject}})
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["fired"], fired)

    def test_simulation_rejects_unknown_event_field(self):
        status, _, raw = self.post("/api/simulate", {"hook": valid_hook(), "event": {"trigger": "PostFileSave", "subject": "a.py", "execute": True}})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["status"], "invalid_event")

    def test_backend_nonexecution_with_marker_and_spies(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / "bad.txt"
            hook = valid_hook()
            hook["action"]["command"] = f'python -c "from pathlib import Path; Path(r\'{marker}\').touch()"'
            with mock.patch("subprocess.run", side_effect=AssertionError("executed")), mock.patch("subprocess.Popen", side_effect=AssertionError("executed")), mock.patch("os.system", side_effect=AssertionError("executed")):
                status, _, raw = self.post("/api/simulate", {"hook": hook, "event": {"trigger": "PostFileSave", "subject": "a.py"}})
                export_status, _, export_raw = self.post("/api/export", {"hook": hook})
            self.assertEqual(status, 200)
            self.assertEqual(export_status, 200)
            self.assertTrue(json.loads(raw)["fired"])
            self.assertIn("command", json.loads(export_raw)["content"])
            self.assertFalse(marker.exists())

    def test_export_safe_name_and_invalid_content(self):
        status, _, raw = self.post("/api/export", {"hook": valid_hook(), "filename": "../../My Hook"})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["filename"], "my-hook.json")
        self.assertEqual(data["path"], ".kiro/hooks/my-hook.json")
        self.assertEqual(json.loads(data["content"])["version"], "v1")

        status, _, raw = self.post("/api/export", {"hook": {"name": ""}})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertFalse(data["ok"])
        self.assertTrue(data["errors"])

    def test_no_error_details_or_stack_traces(self):
        _, _, raw = self.post("/api/validate", b"not-json")
        text = raw.decode("utf-8")
        self.assertNotIn("Traceback", text)
        self.assertNotIn("server.py", text)


if __name__ == "__main__":
    unittest.main()
