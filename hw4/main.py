import os
import json
import logging

import functions_framework
from flask import Response
from google.cloud import storage
from google.cloud import pubsub_v1

TOPIC_ID = os.environ.get("TOPIC_ID", "hw3-forbidden-requests")
PROJECT_ID = os.environ.get("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT", ""))

pubsub_publisher = pubsub_v1.PublisherClient()
topic_path = pubsub_publisher.topic_path(PROJECT_ID, TOPIC_ID)

# Use Environment variables set at deploy time
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
BUCKET_PREFIX = os.environ.get("BUCKET_PREFIX", "").lstrip("/")  # optional "directory" prefix

# Cloud Logging captures stdout/stderr automatically in Cloud Functions
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hw3_service1")

storage_client = storage.Client()

def log_struct(event_type: str, **fields) -> None:
    """
    Structured log (JSON). Shows up in Cloud Logging as jsonPayload if emitted as JSON string.
    """
    payload = {"event_type": event_type, **fields}
    logger.info(json.dumps(payload))

@functions_framework.http
def file_reader(request):
    #  only GET is implemented
    if request.method != "GET":
        log_struct(
            "method_not_implemented",
            method=request.method,
            path=request.path,
            query=request.query_string.decode("utf-8", errors="ignore"),
            user_agent=request.headers.get("User-Agent", ""),
        )
        print(f"501 not implemented: method={request.method} path={request.path}")
        return Response("501 Not Implemented\n", status=501, mimetype="text/plain")

    FORBIDDEN = {
    "North Korea", "Iran", "Cuba", "Myanmar", "Iraq",
    "Libya", "Sudan", "Zimbabwe", "Syria"
    }

    country = request.headers.get("X-country", "").strip()

    if country in FORBIDDEN:
        print(f"400 permission denied: forbidden country={country} path={request.path}")

        msg = {
            "event_type": "forbidden_country",
            "country": country,
            "path": request.path,
        }

        try:
            payload = json.dumps(msg).encode("utf-8")
            msg_id = pubsub_publisher.publish(topic_path, payload).result(timeout=5)
            print(f"Published forbidden request message_id={msg_id} topic={TOPIC_ID}")
        except Exception as e:
            print(f"ERROR publishing to Pub/Sub: {e}")

        return Response("400 Permission Denied\n", status=400, mimetype="text/plain")


    print(f"DEBUG X-country header received: '{request.headers.get('X-country', '')}'")
    filename = request.args.get("file", "").lstrip("/")

    if not filename:
        filename = request.path.lstrip("/")

    if not filename:
        log_struct(
            "file_not_found",
            reason="missing_filename",
            path=request.path,
            query=request.query_string.decode("utf-8", errors="ignore"),
        )
        print("404 not found: missing filename (no query param and path was '/')")
        return Response("404 Not Found\n", status=404, mimetype="text/plain")             

    filename = filename.lstrip("/")
    object_name = f"{BUCKET_PREFIX}/{filename}" if BUCKET_PREFIX else filename

    print(f"DEBUG filename={filename} object_name={object_name} path={request.path} query={request.query_string}")

    # Fetch from GCS and return contents
    try:
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(object_name)

        if not blob.exists():
            log_struct(
                "file_not_found",
                bucket=BUCKET_NAME,
                object=object_name,
            )
            print(f"404 not found: gs://{BUCKET_NAME}/{object_name}")
            return Response("404 Not Found\n", status=404, mimetype="text/plain")

        data = blob.download_as_bytes()

        # structured log for successful reads
        log_struct(
            "file_served",
            bucket=BUCKET_NAME,
            object=object_name,
            bytes=len(data),
        )

        return Response(data, status=200, mimetype="application/octet-stream")

    except Exception as e:
        # implemented 500 error handling for debugging purposes 
        log_struct(
            "internal_error",
            error=str(e),
            bucket=BUCKET_NAME,
            object=object_name,
        )
        print(f"500 internal error: {e}")
        return Response("500 Internal Server Error\n", status=500, mimetype="text/plain")