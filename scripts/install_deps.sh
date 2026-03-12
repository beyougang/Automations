#!/usr/bin/env bash
set -euo pipefail

# 自动安装 Python 依赖：
# 1) 优先使用环境中的 HTTP(S)_PROXY
# 2) 失败时自动切换到常见镜像源

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REQ_FILE="${ROOT_DIR}/requirements.txt"
PYTHON_BIN="${PYTHON_BIN:-python3}"

if [[ ! -f "${REQ_FILE}" ]]; then
  echo "requirements.txt 不存在: ${REQ_FILE}" >&2
  exit 1
fi

PIP_INSTALL_BASE=("${PYTHON_BIN}" -m pip install --upgrade pip)
echo ">>> 升级 pip"
"${PIP_INSTALL_BASE[@]}"

echo ">>> 尝试安装依赖（默认索引）"
if "${PYTHON_BIN}" -m pip install -r "${REQ_FILE}"; then
  echo "✅ 依赖安装成功（默认索引）"
  exit 0
fi

echo "⚠️ 默认索引安装失败，开始尝试镜像源..."

MIRRORS=(
  "https://pypi.tuna.tsinghua.edu.cn/simple"
  "https://mirrors.aliyun.com/pypi/simple"
)

for mirror in "${MIRRORS[@]}"; do
  echo ">>> 尝试镜像: ${mirror}"
  if "${PYTHON_BIN}" -m pip install -r "${REQ_FILE}" -i "${mirror}" --trusted-host "$(echo "${mirror}" | awk -F/ '{print $3}')"; then
    echo "✅ 依赖安装成功（镜像: ${mirror}）"
    exit 0
  fi
done

cat <<'EOF'
❌ 依赖安装仍失败，请检查：
1) 代理是否可用：
   export HTTPS_PROXY=http://<proxy_host>:<port>
   export HTTP_PROXY=http://<proxy_host>:<port>
2) DNS 与 TLS 证书（企业内网常见问题）。
3) 是否可访问 pypi.org 或镜像域名。

也可以配置 pip 全局镜像：
  mkdir -p ~/.pip
  cat > ~/.pip/pip.conf <<CONF
[global]
index-url = https://pypi.tuna.tsinghua.edu.cn/simple
trusted-host = pypi.tuna.tsinghua.edu.cn
timeout = 120
CONF
EOF

exit 1
