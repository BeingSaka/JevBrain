import json
import sys
import tempfile
import threading
import unittest
from http import HTTPStatus
from http.client import HTTPConnection
from pathlib import Path
from unittest.mock import patch

from app import adapter
from app.adapter import evaluate
from app.server import JevHTTPServer, JevRequestHandler
from jev_engine.logging import JsonlLogger
from jev_engine.normalize import EngineError

ROOT = Path(__file__).resolve().parents[2]
TESTS_DIR = str(ROOT / "tests")
if TESTS_DIR not in sys.path:
    sys.path.insert(0, TESTS_DIR)
from test_engine import Evaluator, Worker, answer


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.logger_patch = patch(
            "app.adapter.JsonlLogger",
            side_effect=lambda _: JsonlLogger(Path(self.temp_dir.name) / "evaluations.jsonl"),
        )
        self.logger_patch.start()
        self.addCleanup(self.logger_patch.stop)
        self.payload = {
            "original_request": "Write a concise launch message using the supplied facts.",
            "locked_requirements": [
                "Mention Atlas and its launch date.",
                "Do not invent prices."
            ],
            "candidate_output": "Atlas launches soon. It costs $10.",
            "output_type": "text",
            "available_evidence": "Atlas launches on 15 October 2026. Price has not been announced.",
            "known_constraints": ["Maximum 200 characters."],
            "deterministic_checks": {"max_chars": 200},
        }

    def test_job_duration_and_scope(self):
        client = Evaluator([answer()])
        with patch("app.adapter.JevClient", return_value=client), patch("app.adapter.configured_worker", return_value=None):
            response = evaluate(self.payload)
        self.assertTrue(response["ok"])
        self.assertGreater(response["job_duration_ms"], 0)
        self.assertIsInstance(response["job_duration_ms"], float)
        self.assertEqual(response["job_duration_scope"], adapter.JOB_DURATION_SCOPE)
        self.assertIn("payload normalization and validation", response["job_duration_scope"])
        self.assertIn("excludes response serialization", response["job_duration_scope"])

    def test_v1_authority_preserved(self):
        client = Evaluator([answer()])
        with patch("app.adapter.JevClient", return_value=client), patch("app.adapter.configured_worker", return_value=None):
            response = evaluate(self.payload)
        self.assertTrue(response["ok"])
        self.assertIn("decision", response["result"])

    def test_fr006_deterministic_failure_skips_semantic_evaluation(self):
        payload = {
            "original_request": "Return valid JSON.",
            "locked_requirements": ["Return valid JSON."],
            "candidate_output": "not json",
            "output_type": "text",
            "deterministic_checks": {"valid_json": True},
        }
        client = Evaluator([])
        with patch("app.adapter.JevClient", return_value=client), patch("app.adapter.configured_worker", return_value=None):
            response = evaluate(payload)
        self.assertTrue(response["ok"])
        result = response["result"]
        self.assertIsNone(result["history"][0]["jev_results"])
        self.assertEqual(client.calls, 0)
        self.assertEqual(result["worker_calls"], [])

    def test_fr006_control_calls_semantic_client_and_worker(self):
        payload = {
            "original_request": "Return valid JSON.",
            "locked_requirements": ["Return valid JSON."],
            "candidate_output": "not json",
            "output_type": "text",
            "deterministic_checks": {"valid_json": True},
        }
        client = Evaluator([answer(False), answer()])
        worker = Worker(['{"message":"fixed"}', '{"message":"fixed","status":"ok"}'])
        with patch("app.adapter.JevClient", return_value=client), patch("app.adapter.configured_worker", return_value=worker):
            response = evaluate(payload)
        self.assertTrue(response["ok"])
        self.assertGreater(client.calls, 0)
        self.assertGreater(len(worker.payloads), 0)
        self.assertGreater(len(response["result"]["worker_calls"]), 0)

    def test_provider_failures_are_structured_without_decisions(self):
        for signal, error_type in (
            ("TYPESAFE_API_KEY is not configured", "provider_config"),
            ("Provider connection/timeout failure; not retried to avoid duplicate billing", "provider"),
        ):
            with self.subTest(error_type=error_type):
                client = Evaluator([EngineError(signal)])
                with patch("app.adapter.JevClient", return_value=client), patch("app.adapter.configured_worker", return_value=None):
                    response = evaluate(self.payload)
                self.assertFalse(response["ok"])
                self.assertEqual(response["error"]["type"], error_type)
                self.assertNotIn("decision", response)
                self.assertNotIn(signal, response["error"]["message"])

    def test_missing_required_field(self):
        bad = dict(self.payload)
        bad.pop("original_request")
        response = evaluate(bad)
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "validation")
        self.assertNotIn("decision", response)

    def test_invalid_json_payload(self):
        response = evaluate("bad")
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"]["type"], "validation")
        self.assertNotIn("decision", response)


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = JevHTTPServer(("127.0.0.1", 0), JevRequestHandler)
        cls.port = cls.server.server_address[1]
        cls.server.cli_args = adapter.parse_cli_args()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    @staticmethod
    def _request(host, port, path, body=None, headers=None):
        conn = HTTPConnection(host, port, timeout=5)
        try:
            headers = headers or {}
            if body is not None:
                body_bytes = json.dumps(body).encode("utf-8")
                headers["Content-Length"] = str(len(body_bytes))
            else:
                body_bytes = None
            conn.request("POST" if body is not None else "GET", path, body=body_bytes, headers=headers)
            return conn.getresponse()
        finally:
            conn.close()

    def test_bad_host_rejected(self):
        response = self._request(
            "127.0.0.1",
            self.port,
            "/api/evaluate",
            body={"original_request": "x"},
            headers={
                "Host": "example.com:8765",
                "Content-Type": "application/json",
                "Origin": f"http://127.0.0.1:{self.port}",
            },
        )
        self.assertEqual(response.status, HTTPStatus.FORBIDDEN)

    def test_bad_origin_rejected(self):
        with patch("app.server.evaluate", return_value={
            "ok": True,
            "result": {"decision": "PASS"},
            "job_duration_ms": 0.1,
            "job_duration_scope": "includes engine setup and all repair attempts",
        }):
            response = self._request(
                "127.0.0.1",
                self.port,
                "/api/evaluate",
                body={"original_request": "x"},
                headers={
                    "Host": f"127.0.0.1:{self.port}",
                    "Content-Type": "application/json",
                    "Origin": "http://example.com",
                },
            )
            self.assertEqual(response.status, HTTPStatus.FORBIDDEN)

        def test_missing_origin_rejected(self):
            response = self._request(
                "127.0.0.1",
                self.port,
                "/api/evaluate",
                body={"original_request": "x"},
                headers={"Host": f"127.0.0.1:{self.port}", "Content-Type": "application/json"},
            )
            self.assertEqual(response.status, HTTPStatus.FORBIDDEN)

        def test_malformed_origin_rejected(self):
            response = self._request(
                "127.0.0.1",
                self.port,
                "/api/evaluate",
                body={"original_request": "x"},
                headers={
                    "Host": f"127.0.0.1:{self.port}",
                    "Content-Type": "application/json",
                    "Origin": "http://[invalid",
                },
            )
            self.assertEqual(response.status, HTTPStatus.FORBIDDEN)

        def test_wrong_content_type_rejected(self):
            response = self._request(
                "127.0.0.1",
                self.port,
                "/api/evaluate",
                body={"original_request": "x"},
                headers={
                    "Host": f"127.0.0.1:{self.port}",
                    "Content-Type": "text/plain",
                    "Origin": f"http://127.0.0.1:{self.port}",
                },
            )
            self.assertEqual(response.status, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)

        def test_provider_error_maps_to_generic_503(self):
            with patch("app.server.evaluate", return_value={
                "ok": False,
                "error": {"type": "provider", "message": "sensitive provider detail"},
            }):
                response = self._request(
                    "127.0.0.1",
                    self.port,
                    "/api/evaluate",
                    body={"original_request": "x"},
                    headers={
                        "Host": f"127.0.0.1:{self.port}",
                        "Content-Type": "application/json",
                        "Origin": f"http://127.0.0.1:{self.port}",
                    },
                )
                payload = json.loads(response.read())
            self.assertEqual(response.status, HTTPStatus.SERVICE_UNAVAILABLE)
            self.assertEqual(payload["error"]["message"], "Evaluation provider is unavailable")
            self.assertNotIn("decision", payload)

    def test_path_outside_allowlist_rejected(self):
        response = self._request(
            "127.0.0.1",
            self.port,
            "/forbidden",
            headers={
                "Host": f"127.0.0.1:{self.port}",
                "Origin": f"http://127.0.0.1:{self.port}",
            },
        )
        self.assertEqual(response.status, HTTPStatus.NOT_FOUND)


if __name__ == "__main__":
    unittest.main()
