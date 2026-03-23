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
BUCKET_PREFIX="$(get_md bucket-prefix || true)"
REPORTER_URL="$(get_md reporter-url)"
APP_DIR="/opt/hw4repo"
VENV_DIR="/opt/hw4venv"

apt-get update
apt-get install -y git python3 python3-pip python3-venv

rm -rf "${APP_DIR}"
git clone --branch "${REPO_BRANCH}" "${REPO_URL}" "${APP_DIR}"

python3 -m venv "${VENV_DIR}"
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${APP_DIR}/hw4/requirements.txt"

export HOST=0.0.0.0
export PORT=8080
export REQUEST_QUEUE_SIZE=32
export BUCKET_NAME="${BUCKET_NAME}"
export BUCKET_PREFIX="${BUCKET_PREFIX}"
export REPORTER_URL="${REPORTER_URL}"
export LOG_LEVEL=INFO

touch /var/log/startup_already_done

exec "${VENV_DIR}/bin/python" "${APP_DIR}/hw4/service1_vm.py"