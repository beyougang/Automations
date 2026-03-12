#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "用法: $0 <server_user> <server_host> <server_path> [branch]"
  exit 1
fi

SERVER_USER="$1"
SERVER_HOST="$2"
SERVER_PATH="$3"
BRANCH="${4:-main}"

echo ">>> 部署到 ${SERVER_USER}@${SERVER_HOST}:${SERVER_PATH} (branch=${BRANCH})"

ssh "${SERVER_USER}@${SERVER_HOST}" "mkdir -p ${SERVER_PATH}"

if ssh "${SERVER_USER}@${SERVER_HOST}" "[ -d ${SERVER_PATH}/.git ]"; then
  ssh "${SERVER_USER}@${SERVER_HOST}" "cd ${SERVER_PATH} && git fetch --all && git checkout ${BRANCH} && git pull origin ${BRANCH}"
else
  REPO_URL="$(git config --get remote.origin.url)"
  ssh "${SERVER_USER}@${SERVER_HOST}" "git clone -b ${BRANCH} ${REPO_URL} ${SERVER_PATH}"
fi

ssh "${SERVER_USER}@${SERVER_HOST}" "cd ${SERVER_PATH} && docker compose up -d --build"

echo "✅ 部署完成，服务已通过 docker compose 启动"
