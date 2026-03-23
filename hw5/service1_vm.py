#!/usr/bin/env python3
import json
import logging
import mimetypes
import os
import urllib.parse
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.cloud import logging as cloud_logging
from google.cloud import storage

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", "8080"))

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "").strip("/")
REPORTER_URL = os.environ.get("REPORTER_URL", "")
REQUEST_QUEUE_SIZE = int(os.environ.get("REQUEST_QUEUE_SIZE", "32"))
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

FORBIDDEN_COUNTRIES = {
    "North Korea",
    "Iran",
    "Cuba",
    "Myanmar",
    "Iraq",
    "Libya",
    "Sudan",
    "Zimbabwe",
    "Syria",
}

if not BUCKET_NAME:
    raise RuntimeError("BUCKET_NAME must be set")

cloud_logging.Client().setup_logging()
logger = logging.getLogger("hw4_service1")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))
storage_client = storage.Client()


def log_struct(severity: str, event_type: str, **fields) -> None:
    payload = {"event_type": event_type, **fields}
    fn = getattr(logger, severity.lower(), logger.info)
    fn(json.dumps(payload))


def build_object_name(filename: str) -> str:
    filename = filename.lstrip("/")
    if BUCKET_PREFIX:
        return f"{BUCKET_PREFIX}/{filename}"
    return filename


def guess_content_type(filename: str) -> str:
    content_type, _ = mimetypes.guess_type(filename)
    return content_type or "application/octet-stream"


def notify_reporter(country: str, path: str, method: str, client_ip: str) -> None:
    if not REPORTER_URL:
        log_struct("warning", "reporter_not_configured", path=path, country=country)
        return

    payload = {
        "event_type": "forbidden_country",
        "country": country,
        "path": path,
        "method": method,
        "client_ip": client_ip,
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        REPORTER_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            _ = resp.read()
            log_struct(
                "info",
                "reporter_notified",
                reporter_url=REPORTER_URL,
                reporter_status=resp.status,
                country=country,
                path=path,
            )
    except Exception as exc:
        log_struct(
            "error",
            "reporter_notify_failed",
            reporter_url=REPORTER_URL,
            country=country,
            path=path,
            error=str(exc),
        )


class CustomThreadingHTTPServer(ThreadingHTTPServer):
    request_queue_size = REQUEST_QUEUE_SIZE
    daemon_threads = True
    allow_reuse_address = True


class FileServerHandler(BaseHTTPRequestHandler):
    server_version = "HW4FileServer/1.0"
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

    def _client_ip(self) -> str:
        return self.client_address[0] if self.client_address else ""

    def _send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, status: int, text: str) -> None:
        self._send_bytes(status, text.encode("utf-8"), "text/plain; charset=utf-8")

    def _not_implemented(self) -> None:
        log_struct(
            "warning",
            "method_not_implemented",
            method=self.command,
            path=self.path,
            client_ip=self._client_ip(),
        )
        self._send_text(HTTPStatus.NOT_IMPLEMENTED, "501 Not Implemented\n")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        client_ip = self._client_ip()
        country = self.headers.get("X-country", "").strip()

        if country in FORBIDDEN_COUNTRIES:
            log_struct(
                "critical",
                "forbidden_country",
                country=country,
                path=self.path,
                method=self.command,
                client_ip=client_ip,
            )
            notify_reporter(country, self.path, self.command, client_ip)
            self._send_text(HTTPStatus.BAD_REQUEST, "400 Permission Denied\n")
            return

        filename = params.get("file", [""])[0].lstrip("/")
        if not filename:
            filename = parsed.path.lstrip("/")

        if not filename:
            log_struct(
                "warning",
                "file_not_found",
                reason="missing_filename",
                path=self.path,
                client_ip=client_ip,
            )
            self._send_text(HTTPStatus.NOT_FOUND, "404 Not Found\n")
            return

        object_name = build_object_name(filename)

        try:
            bucket = storage_client.bucket(BUCKET_NAME)
            blob = bucket.blob(object_name)

            if not blob.exists():
                log_struct(
                    "warning",
                    "file_not_found",
                    bucket=BUCKET_NAME,
                    object=object_name,
                    client_ip=client_ip,
                )
                self._send_text(HTTPStatus.NOT_FOUND, "404 Not Found\n")
                return

            data = blob.download_as_bytes()
            content_type = blob.content_type or guess_content_type(filename)

            log_struct(
                "info",
                "file_served",
                bucket=BUCKET_NAME,
                object=object_name,
                bytes=len(data),
                client_ip=client_ip,
            )
            self._send_bytes(HTTPStatus.OK, data, content_type)
        except Exception as exc:
            log_struct(
                "error",
                "internal_error",
                bucket=BUCKET_NAME,
                object=object_name,
                error=str(exc),
                client_ip=client_ip,
            )
            self._send_text(HTTPStatus.INTERNAL_SERVER_ERROR, "500 Internal Server Error\n")

    def do_POST(self) -> None:
        self._not_implemented()

    def do_PUT(self) -> None:
        self._not_implemented()

    def do_DELETE(self) -> None:
        self._not_implemented()

    def do_HEAD(self) -> None:
        self._not_implemented()

    def do_CONNECT(self) -> None:
        self._not_implemented()

    def do_OPTIONS(self) -> None:
        self._not_implemented()

    def do_TRACE(self) -> None:
        self._not_implemented()

    def do_PATCH(self) -> None:
        self._not_implemented()


def main() -> None:
    server = CustomThreadingHTTPServer((HOST, PORT), FileServerHandler)
    logger.info(
        json.dumps(
            {
                "event_type": "server_start",
                "host": HOST,
                "port": PORT,
                "bucket_name": BUCKET_NAME,
                "bucket_prefix": BUCKET_PREFIX,
                "reporter_url": REPORTER_URL,
                "request_queue_size": server.request_queue_size,
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