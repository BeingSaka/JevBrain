#!/usr/bin/env python3
"""
JevBrain Decision Console - Local Zero-Cost HTTP Server

MODES:

PRIMARY / FULL MODE:
python dashboard/server.py
This provides:
- dashboard static assets
- /api/result
- /api/logs
- live local result/log integration

STATIC-ONLY MODE:
python -m http.server 8080 --directory dashboard
This may be used only for:
- bundled fixtures
- file upload
- pasted JSON
It does NOT provide /api/result or /api/logs.
"""

import http.server
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DASHBOARD_DIR = Path(__file__).resolve().parent

class DecisionConsoleHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        # Route API endpoints (read-only, fixed repository paths)
        if self.path in ("/api/result", "/result.json"):
            self.serve_result_json()
        elif self.path == "/api/logs":
            self.serve_evaluations_log()
        else:
            # Fall back to serving static files strictly from dashboard/ directory
            super().do_GET()

    def do_POST(self):
        self.send_error(405, "Method Not Allowed: Console server API is read-only")

    def do_PUT(self):
        self.send_error(405, "Method Not Allowed: Console server API is read-only")

    def do_DELETE(self):
        self.send_error(405, "Method Not Allowed: Console server API is read-only")

    def do_PATCH(self):
        self.send_error(405, "Method Not Allowed: Console server API is read-only")

    def serve_result_json(self):
        result_file = REPO_ROOT / "result.json"
        if not result_file.is_file():
            self.send_json_response({"error": "result.json not found in repository root", "exists": False}, status=404)
            return
        try:
            content = result_file.read_text(encoding="utf-8")
            data = json.loads(content)
            self.send_json_response(data, status=200)
        except Exception as e:
            self.send_json_response({"error": f"Failed to parse result.json: {e}"}, status=500)

    def serve_evaluations_log(self):
        log_file = REPO_ROOT / "logs" / "evaluations.jsonl"
        if not log_file.is_file():
            self.send_json_response({"error": "logs/evaluations.jsonl not found", "events": []}, status=404)
            return
        try:
            lines = [l.strip() for l in log_file.read_text(encoding="utf-8").splitlines() if l.strip()]
            events = []
            # Return up to last 50 events in reverse chronological order
            for l in reversed(lines[-50:]):
                try:
                    events.append(json.loads(l))
                except Exception:
                    pass
            self.send_json_response({"total": len(lines), "events": events}, status=200)
        except Exception as e:
            self.send_json_response({"error": f"Failed to read logs: {e}", "events": []}, status=500)

    def send_json_response(self, data, status=200):
        body = json.dumps(data, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Keep server output clean and concise
        sys.stderr.write(f"[Console Server] {format % args}\n")

def run(port=8080):
    host = "127.0.0.1"  # Bind strictly to local loopback
    for p in range(port, port + 10):
        try:
            server = http.server.ThreadingHTTPServer((host, p), DecisionConsoleHandler)
            print(f"=" * 64)
            print(f" JEVBRAIN DECISION CONSOLE V1 (FULL SERVER MODE)")
            print(f"=" * 64)
            print(f" Local URL:       http://{host}:{p}/")
            print(f" Repository root: {REPO_ROOT}")
            print(f" Live Endpoints:  /api/result, /api/logs")
            print(f" Security:        Bound to 127.0.0.1 | Read-Only API")
            print(f"-" * 64)
            print(f" Note on execution modes:")
            print(f" - FULL MODE:        python dashboard/server.py")
            print(f"   (Static assets + /api/result + /api/logs + live file integration)")
            print(f" - STATIC-ONLY MODE: python -m http.server {p} --directory dashboard")
            print(f"   (Fixtures, file upload, pasted JSON only; NO /api/ endpoints)")
            print(f"=" * 64)
            print(f" Press Ctrl+C to stop.")
            print(f"=" * 64)
            sys.stdout.flush()
            server.serve_forever()
            break
        except OSError as e:
            if e.errno == 98 or getattr(e, 'winerror', None) == 10048:
                continue
            raise

if __name__ == "__main__":
    port_arg = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 8080
    try:
        run(port_arg)
    except KeyboardInterrupt:
        print("\n[Console Server] Shutting down.")
        sys.exit(0)
