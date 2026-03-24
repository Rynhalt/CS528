#!/bin/bash
set -euo pipefail

exec > >(tee /var/log/startup-script.log) 2>&1

if [ -f /var/log/startup_already_done ]; then
    echo "Startup script already ran once. Skipping."
    exit 0
fi

get_md() {
    curl -fs -H "Metadata-Flavor: Google" \
      "http://metadata.google.internal/computeMetadata/v1/instance/attributes/$1"
}

REPO_URL="$(get_md repo-url)"
REPO_BRANCH="$(get_md repo-branch)"
BUCKET_NAME="$(get_md bucket-name)"
LOG_OBJECT="$(get_md log-object)"

APP_DIR="/opt/hw5repo"
VENV_DIR="/opt/hw5venv"

# ---- SETUP ----
apt-get update
apt-get install -y git python3 python3-pip python3-venv ca-certificates

rm -rf "${APP_DIR}"
git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${APP_DIR}"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/hw5/requirements.txt"

# ---- RUN ----
cd "${APP_DIR}/hw5"

export HOST=0.0.0.0
export PORT=9090
export REQUEST_QUEUE_SIZE=32
export BUCKET_NAME="${BUCKET_NAME}"
export LOG_OBJECT="${LOG_OBJECT}"
export LOG_LEVEL=INFO
export GOOGLE_CLOUD_PROJECT="$(curl -fs -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/project/project-id)"

exec "${VENV_DIR}/bin/python" service2_vm.py \
  >> /var/log/service2.log 2>&1 &

touch /var/log/startup_already_done