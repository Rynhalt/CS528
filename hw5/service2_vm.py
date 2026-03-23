#!/usr/bin/env python3
import json
import logging
import os
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.api_core.exceptions import NotFound, PreconditionFailed
from google.cloud import logging as cloud_logging
from google.cloud import storage

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "9090"))
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
LOG_OBJECT = os.environ.get("LOG_OBJECT", "forbidden-logs/forbidden.log")
REQUEST_QUEUE_SIZE = int(os.environ.get("REQUEST_QUEUE_SIZE", "32"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("PROJECT_ID")
if not PROJECT_ID:
    raise RuntimeError("GOOGLE_CLOUD_PROJECT or PROJECT_ID must be set")

cloud_logging.Client(project=PROJECT_ID).setup_logging()
logger = logging.getLogger("hw4_service2")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
storage_client = storage.Client()


def append_line_to_gcs(bucket_name: str, object_name: str, line: str) -> None:
    if not bucket_name:
        return

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    for attempt in range(10):
        try:
            try:
                blob.reload()
                generation = blob.generation
                existing = blob.download_as_text()
            except NotFound:
                generation = 0
                existing = ""

            new_contents = existing + line + "\n"
            if generation == 0:
                blob.upload_from_string(new_contents, if_generation_match=0)
            else:
                blob.upload_from_string(new_contents, if_generation_match=generation)
            return
        except PreconditionFailed:
            time.sleep(0.2 * (attempt + 1))

    raise RuntimeError("Failed to append forbidden log after retries")


class CustomThreadingHTTPServer(ThreadingHTTPServer):
    request_queue_size = REQUEST_QUEUE_SIZE
    daemon_threads = True
    allow_reuse_address = True


class ReporterHandler(BaseHTTPRequestHandler):
    server_version = "HW4Reporter/1.0"
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args) -> None:
        logger.info(
            json.dumps(
                {
                    "event_type": "access_log",
                    "client_ip": self.client_address[0] if self.client_address else "",
                    "request_line": self.requestline,
                    "message": fmt % args,
                }
            )
        )

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str) -> None:
        self._send_bytes(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def do_GET(self) -> None:
        if self.path == "/healthz":
            self._send_text(HTTPStatus.OK, "ok\n")
        else:
            self._send_text(HTTPStatus.NOT_FOUND, "404 Not Found\n")

    def do_POST(self) -> None:
        if self.path != "/report":
            self._send_text(HTTPStatus.NOT_FOUND, "404 Not Found\n")
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0

        raw_body = self.rfile.read(content_length) if content_length > 0 else b""

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            logger.warning(json.dumps({"event_type": "bad_json"}))
            self._send_text(HTTPStatus.BAD_REQUEST, "400 Bad Request\n")
            return

        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = (
            f"{ts} "
            f"event_type={payload.get('event_type', '')} "
            f"country={payload.get('country', '')} "
            f"path={payload.get('path', '')} "
            f"method={payload.get('method', '')} "
            f"client_ip={payload.get('client_ip', '')}"
        )

        print(f"FORBIDDEN REQUEST RECEIVED: {line}", flush=True)

        logger.error(
            json.dumps({"event_type": "forbidden_request_received", "payload": payload})
        )

        try:
            if BUCKET_NAME:
                append_line_to_gcs(BUCKET_NAME, LOG_OBJECT, line)
        except Exception as exc:
            logger.error(
                json.dumps(
                    {
                        "event_type": "append_failed",
                        "error": str(exc),
                        "bucket_name": BUCKET_NAME,
                        "log_object": LOG_OBJECT,
                    }
                )
            )
            self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "500 Internal Server Error\n")
            return

        self._send_text(HTTPStatus.OK, "200 OK\n")

    def do_PUT(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_DELETE(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_HEAD(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_CONNECT(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_OPTIONS(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_TRACE(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_PATCH(self) -> None:
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")


def main() -> None:
    server = CustomThreadingHTTPServer((HOST, PORT), ReporterHandler)
    logger.info(
        json.dumps(
            {
                "event_type": "server_start",
                "host": HOST,
                "port": PORT,
                "request_queue_size": server.request_queue_size,
                "bucket_name": BUCKET_NAME,
                "log_object": LOG_OBJECT,
            }
        )
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()