# CS528 HW3 Microservices Walkthrough

This document explains how the two Python services in this repo satisfy the homework requirements, especially steps 1–8. Replace placeholder names (bucket, topic, etc.) with your actual resource identifiers before turning in the PDF.

## Service 1 – Cloud Function (steps 1–3)
- File: `main.py`. Deploy as an HTTP-triggered Cloud Function (2nd gen) that runs under a dedicated service account with read access to your HW2 bucket and publish access to the Pub/Sub topic.
- Environment variables set at deploy time:
  - `BUCKET_NAME` – HW2 bucket name.
  - `BUCKET_PREFIX` – optional prefix (folder) inside the bucket.
  - `TOPIC_ID` – Pub/Sub topic that the second service subscribes to.
- Behavior:
  - Accepts only GET (`request.method` check). Non-GET returns `501 Not Implemented` and logs a structured event via `log_struct(...)` (step 3).
  - Resolves the file either from `?file=` or from the path component and fetches it from Cloud Storage using `google.cloud.storage`. Missing files emit structured `file_not_found` logs and return `404` (step 2).
  - Successful downloads return the blob bytes with status `200` (step 1) and log a `file_served` structured entry for Cloud Logging screenshots.

## Step 4 – Provided HTTP client (100 GETs)
Use the instructor-provided `http-client` binary against the Cloud Function URL. Example:
```bash
./http-client \
  --url "https://REGION-PROJECT.cloudfunctions.net/file_reader" \
  --requests 100 \
  --file sample.txt
```
Capture a terminal screenshot; for the report you can note that the screenshot shows 5 requests for readability but you ran 100.

## Step 5 – curl demos for 404 and 501
Use curl against the function URL while varying method/path:
```bash
# 404: request a missing object
curl -i "https://REGION-PROJECT.cloudfunctions.net/file_reader?file=missing.txt"

# 501: use POST (or any unsupported method)
curl -i -X POST "https://REGION-PROJECT.cloudfunctions.net/file_reader"
```
Take terminal screenshots showing the HTTP status lines for the PDF and include links to the matching Cloud Logging entries.

## Step 6 – Browser screenshots (200/404/501)
- 200 case: browse to `https://.../file_reader?file=existing.txt`; the browser should download the object immediately. Capture the download prompt.
- 404 case: browse to a missing file; screenshot the 404 text in the browser.
- 501 case: use a REST client tab (or browser extension) to issue a POST and screenshot the 501 response.

## Step 7 – Forbidden-country filtering and Pub/Sub
- `main.py` reads `X-country` from HTTP headers. The forbidden list matches the assignment (North Korea, Iran, Cuba, Myanmar, Iraq, Libya, Sudan, Zimbabwe, Syria).
- Forbidden requests trigger:
  1. Immediate `400 Permission Denied` response to the client.
  2. JSON payload published to the Pub/Sub topic (`hw3-forbidden-requests` by default) using the Cloud Function service account.
  3. Console log (`print(...)`) so the Cloud Logging screenshot can show the event.
- Use curl or the http client to send a header:  
  `curl -i -H "X-country: North Korea" "https://.../file_reader?file=any.txt"`  
  Include this result in the report.

## Service 2 – Local subscriber (step 8)
- File: `service2.py`. Runs on the laptop, subscribes to `hw3-forbidden-sub`, and appends every forbidden event to `gs://<bucket>/forbidden-logs/forbidden.log`. The helper `append_line_to_gcs` uses generation-match so concurrent writers do not lose data.
- The program prints each message to stdout, satisfying the “print an appropriate error message” requirement. Add a terminal screenshot showing the output plus a listing of the log object in the bucket (`gsutil cat gs://.../forbidden-logs/forbidden.log`).

### Service-account impersonation workflow
We cannot run `gcloud auth application-default login`. Instead:
1. Log in as your user once (`gcloud auth login`) – this keeps user credentials locally.
2. Grant that user the `roles/iam.serviceAccountTokenCreator` role on the Cloud Function service account.
3. Before launching `service2.py`, mint a short-lived token that impersonates the service account:
   ```bash
   export IMPERSONATED_SA="sa-name@PROJECT.iam.gserviceaccount.com"
   export GOOGLE_OAUTH_ACCESS_TOKEN=$(gcloud auth print-access-token \
     --impersonate-service-account="${IMPERSONATED_SA}")
   ```
4. Run the subscriber with the token:
   ```bash
   python3 service2.py
   ```
The code creates `google.oauth2.credentials.Credentials` from `GOOGLE_OAUTH_ACCESS_TOKEN` and passes them into both Pub/Sub and Cloud Storage clients, so every API call is executed as the impersonated service account. Mention this flow explicitly in the PDF as the answer to step 8, along with why impersonation is chosen (short-lived, no stored keys).

## How to Convert This Report to PDF
Once you add screenshots and any extra commentary, use a Markdown-to-PDF tool such as `pandoc` or Google Docs. Example with pandoc:
```bash
pandoc REPORT.md -o report.pdf
```
Submit the PDF plus the GitHub link to this repository, as required.
