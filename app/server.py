import json
import os
import sys
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

APP_ROOT = Path(__file__).resolve().parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from adapter import evaluate, parse_cli_args

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
ALLOWED_FILES = {
    "/": APP_DIR / "index.html",
    "/index.html": APP_DIR / "index.html",
    "/app.js": APP_DIR / "app.js",
    "/style.css": APP_DIR / "style.css",
}


class JevHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    busy = False
    busy_lock = threading.Lock()


class JevRequestHandler(BaseHTTPRequestHandler):
    server_version = "JevLocalApp/0.1"

    def log_message(self, format, *args):
        return

    def _send_json(self, payload, status_code):
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error_json(self, status_code, error_type, message):
        self._send_json({"ok": False, "error": {"type": error_type, "message": message}}, status_code)

    def _host_allowed(self):
        port = self.server.server_address[1]
        raw_host = self.headers.get("Host")
        if not raw_host or not raw_host.strip():
            return False
        try:
            parsed = urlsplit(f"//{raw_host.strip()}")
            host = parsed.hostname.lower() if parsed.hostname else ""
            parsed_port = parsed.port
        except (ValueError, UnicodeError):
            return False
        return (
            host in {"127.0.0.1", "localhost"}
            and parsed_port == port
            and not parsed.username
            and not parsed.password
            and not parsed.path
            and not parsed.query
            and not parsed.fragment
        )

    def _origin_allowed(self, required=False):
        origin = self.headers.get("Origin")
        if origin is None:
            return not required
        if not origin.strip():
            return False
        try:
            parsed = urlsplit(origin.strip())
            host = parsed.hostname.lower() if parsed.hostname else ""
            port = parsed.port
        except (ValueError, UnicodeError):
            return False
        return (
            parsed.scheme.lower() == "http"
            and host in {"127.0.0.1", "localhost"}
            and port == self.server.server_address[1]
            and parsed.path == ""
            and not parsed.username
            and not parsed.password
            and not parsed.query
            and not parsed.fragment
        )

    def _validate_headers(self, require_origin=False):
        if not self._host_allowed():
            self._error_json(HTTPStatus.FORBIDDEN, "invalid_host", "Invalid Host header")
            return False
        if not self._origin_allowed(required=require_origin):
            self._error_json(HTTPStatus.FORBIDDEN, "invalid_origin", "Invalid Origin header")
            return False
        return True

    def do_GET(self):
        if self.path not in ALLOWED_FILES:
            self._error_json(HTTPStatus.NOT_FOUND, "not_found", "Resource not found")
            return
        if not self._validate_headers():
            return

        file_path = ALLOWED_FILES[self.path]
        try:
            data = file_path.read_bytes()
        except OSError:
            self._error_json(HTTPStatus.NOT_FOUND, "not_found", "Resource not found")
            return

        mime = "text/html; charset=utf-8"
        if self.path.endswith(".js"):
            mime = "application/javascript; charset=utf-8"
        elif self.path.endswith(".css"):
            mime = "text/css; charset=utf-8"

        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path != "/api/evaluate":
            self._error_json(HTTPStatus.NOT_FOUND, "not_found", "Endpoint not found")
            return
        if not self._validate_headers(require_origin=True):
            return
        content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            self._error_json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, "invalid_request", "Content-Type must be application/json")
            return

        content_length = self.headers.get("Content-Length")
        if content_length is None:
            self._error_json(HTTPStatus.BAD_REQUEST, "invalid_request", "Missing Content-Length")
            return
        try:
            length = int(content_length)
        except ValueError:
            self._error_json(HTTPStatus.BAD_REQUEST, "invalid_request", "Invalid Content-Length")
            return
        if length < 0:
            self._error_json(HTTPStatus.BAD_REQUEST, "invalid_request", "Invalid Content-Length")
            return
        if length > 1_048_576:
            self._error_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "payload_too_large", "Request body exceeds 1 MB")
            return

        with JevHTTPServer.busy_lock:
            if JevHTTPServer.busy:
                self._error_json(HTTPStatus.TOO_MANY_REQUESTS, "busy", "Evaluation already in progress")
                return
            JevHTTPServer.busy = True

        try:
            body = self.rfile.read(length)
            if not body:
                self._error_json(HTTPStatus.BAD_REQUEST, "invalid_request", "Empty request body")
                return
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._error_json(HTTPStatus.BAD_REQUEST, "invalid_json", "Malformed JSON body")
                return

            response = evaluate(payload, getattr(self.server, "cli_args", None))
            if not response.get("ok"):
                error = response.get("error", {})
                err_type = error.get("type") if isinstance(error, dict) else None
                if err_type == "provider_config":
                    self._error_json(HTTPStatus.SERVICE_UNAVAILABLE, "provider_config", "Evaluation provider is not configured")
                    return
                if err_type == "provider":
                    self._error_json(HTTPStatus.SERVICE_UNAVAILABLE, "provider", "Evaluation provider is unavailable")
                    return
                if err_type == "validation":
                    self._error_json(HTTPStatus.BAD_REQUEST, "validation", "Invalid evaluation request")
                    return
                self._error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "engine", "Engine evaluation failed")
                return

            self._send_json(response, HTTPStatus.OK)
        except Exception:
            self._error_json(HTTPStatus.INTERNAL_SERVER_ERROR, "engine", "Evaluation failed")
        finally:
            with JevHTTPServer.busy_lock:
                JevHTTPServer.busy = False


def main():
    os.chdir(ROOT)
    args = parse_cli_args(sys.argv[1:])
    host = "127.0.0.1"
    try:
        port = int(os.environ.get("JEV_APP_PORT", "8765"))
        server = JevHTTPServer((host, port), JevRequestHandler)
    except (OSError, ValueError, OverflowError):
        print("Unable to bind the local Jev server; the selected port may be unavailable.", file=sys.stderr)
        raise SystemExit(1) from None

    server.cli_args = args
    try:
        webbrowser.open(f"http://{host}:{port}/")
        server.serve_forever()
    except OSError:
        print("The local Jev server stopped because of a socket error.", file=sys.stderr)
        raise SystemExit(1) from None
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
