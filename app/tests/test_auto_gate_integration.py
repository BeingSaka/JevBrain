import json
import threading
import unittest
from http.client import HTTPConnection
from unittest.mock import patch

from app import server


class AutoGateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.JevHTTPServer(("127.0.0.1", 0), server.JevRequestHandler)
        cls.httpd.cli_args = None
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def _post_request(self, request_text):
        port = self.httpd.server_address[1]
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps({"request_text": request_text}).encode("utf-8")
        connection.request(
            "POST",
            "/api/evaluate",
            body=body,
            headers={
                "Host": f"127.0.0.1:{port}",
                "Origin": f"http://127.0.0.1:{port}",
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
            },
        )
        response = connection.getresponse()
        payload = json.loads(response.read())
        status = response.status
        connection.close()
        return status, payload

    def test_ready_request_reaches_adapter_with_canonical_payload(self):
        adapter_result = {
            "ok": True,
            "result": {
                "decision": "HUMAN REVIEW",
                "reason": "Low semantic confidence",
                "repairs": 0,
                "failed_dimensions": [],
                "final_output": "Generated candidate",
                "semantic_evaluation": {
                    "noul": {"value": 0.5, "confidence": 0.2},
                    "concerns": [],
                },
                "history": [{"failed_dimensions": []}],
            },
            "job_duration_ms": 12.5,
            "job_duration_scope": "test",
        }
        with patch.object(server, "evaluate", return_value=adapter_result) as downstream:
            status, response = self._post_request("Create a 10-second reel.")

        self.assertEqual(status, 200)
        downstream.assert_called_once()
        payload = downstream.call_args.args[0]
        self.assertEqual(
            payload,
            {
                "original_request": "Create a 10-second reel.",
                "locked_requirements": ["10-second"],
                "output_type": "text",
            },
        )
        self.assertNotIn("candidate_output", payload)
        self.assertEqual(response, adapter_result)
        self.assertEqual(response["result"]["decision"], "HUMAN REVIEW")
        self.assertIn("semantic_evaluation", response["result"])
        self.assertIn("job_duration_ms", response)

    def test_clarification_does_not_reach_adapter_and_is_returned(self):
        with patch.object(server, "evaluate") as downstream:
            status, response = self._post_request("Make this better.")

        self.assertEqual(status, 200)
        downstream.assert_not_called()
        self.assertTrue(response["ok"])
        self.assertEqual(response["status"], "NEEDS_CLARIFICATION")
        self.assertTrue(response["clarification_issues"])

    def test_legacy_adapter_payload_path_is_preserved(self):
        legacy_payload = {
            "original_request": "Legacy request.",
            "locked_requirements": ["Keep this exact phrase."],
            "candidate_output": "Existing candidate",
        }
        adapter_result = {"ok": True, "result": {"decision": "PASS"}}
        port = self.httpd.server_address[1]
        connection = HTTPConnection("127.0.0.1", port, timeout=5)
        body = json.dumps(legacy_payload).encode("utf-8")
        with patch.object(server, "evaluate", return_value=adapter_result) as downstream:
            connection.request(
                "POST",
                "/api/evaluate",
                body=body,
                headers={
                    "Host": f"127.0.0.1:{port}",
                    "Origin": f"http://127.0.0.1:{port}",
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                },
            )
            response = connection.getresponse()
            response_body = json.loads(response.read())
            status = response.status
        connection.close()

        self.assertEqual(status, 200)
        downstream.assert_called_once_with(legacy_payload, None)
        self.assertEqual(response_body, adapter_result)


if __name__ == "__main__":
    unittest.main()
