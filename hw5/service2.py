import os
import json
from google.cloud import pubsub_v1
from google.oauth2.credentials import Credentials

PROJECT_ID = "cs528-marcus"
SUBSCRIPTION_ID = "hw3-forbidden-sub"
BUCKET_NAME = "slime123-cs528-hw2"
LOG_OBJECT = "forbidden-logs/forbidden.log"

import time
from google.cloud import storage
from google.api_core.exceptions import PreconditionFailed, NotFound

def append_line_to_gcs(storage_client: storage.Client, bucket_name: str, object_name: str, line: str) -> None:
    """
    Append a single line to a GCS object using generation-match to avoid lost updates.
    Retries on concurrent write conflicts.
    """
    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(object_name)

    for attempt in range(10):
        try:
            # Fetch current contents + generation 
            try:
                blob.reload() 
                generation = blob.generation
                existing = blob.download_as_text()
            except NotFound:
                generation = 0  # 0 means "object must not exist"
                existing = ""

            new_contents = existing + line + "\n"

            # Upload with precondition: only succeed if generation hasn't changed
            if generation == 0:
                blob.upload_from_string(new_contents, if_generation_match=0)
            else:
                blob.upload_from_string(new_contents, if_generation_match=generation)

            return  # success

        except PreconditionFailed:
            # Someone else updated it so retryyy
            time.sleep(0.2 * (attempt + 1))

    raise RuntimeError("Failed to append after multiple retries due to concurrent updates.")

def main():
    token = os.environ.get("GOOGLE_OAUTH_ACCESS_TOKEN", "")
    if not token:
        raise RuntimeError("GOOGLE_OAUTH_ACCESS_TOKEN is not set")

    creds = Credentials(token=token)
    storage_client = storage.Client(credentials=creds)

    subscriber = pubsub_v1.SubscriberClient(credentials=creds)
    sub_path = subscriber.subscription_path(PROJECT_ID, SUBSCRIPTION_ID)

    def callback(message):
        data = message.data.decode("utf-8", errors="replace")
        print(f"RECV message_id={message.message_id} data={data}")

        try:
            event = json.loads(data)
        except Exception:
            event = {"raw": data}

        ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        line = f"{ts} message_id={message.message_id} country={event.get('country','')} path={event.get('path','')} event_type={event.get('event_type','')}"

        try:
            append_line_to_gcs(storage_client, BUCKET_NAME, LOG_OBJECT, line)
            print(f"ACK message_id={message.message_id}")
            message.ack()
        except Exception as e:
            print(f"ERROR before ack message_id={message.message_id}: {e}")
            message.nack()

    print(f"Listening on {sub_path} ... Ctrl+C to stop")
    future = subscriber.subscribe(sub_path, callback=callback)
    try:
        future.result()
    except KeyboardInterrupt:
        future.cancel()
        print("Stopped.")

if __name__ == "__main__":
    main()