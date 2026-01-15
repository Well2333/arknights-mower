#!/usr/bin/env bash
set -euo pipefail

# 设置变量
PORT="${MOWER_PORT:-58000}"
HTTP_PROXY="${HTTP_PROXY:-}"
MAA_DIR="/MAA"
DATA_DIR="/mower-data"
ADB_BIN="${MOWER_ADB_BIN:-/usr/bin/adb}"
SIMULATOR_FOLDER="/simulator"
ARCH="$(uname -m)"

# Token 处理
if [ -n "${MOWER_TOKEN:-}" ] && [ "${MOWER_TOKEN}" != "PLEASE_CHANGE_ME" ]; then
    TOKEN="${MOWER_TOKEN}"
else
  RAND_STR="$(python - <<'PY'
import secrets
import string

alphabet = string.ascii_letters + string.digits
print(''.join(secrets.choice(alphabet) for _ in range(12)))
PY
)"
  TOKEN="mower${RAND_STR}"
    echo "🎲 生成随机 Token: ${TOKEN}"
fi

## 代理环境变量
if [ -n "${HTTP_PROXY}" ]; then
  echo ""
  echo "🌐 检测代理连通性..."
  if curl -s --connect-timeout 3 --proxy "${HTTP_PROXY}" http://httpbin.org/ip >/dev/null 2>&1; then
    echo "✅ 代理连接正常"
    export HTTP_PROXY="${HTTP_PROXY}"
    export HTTPS_PROXY="${HTTP_PROXY}"
  elif curl -s --connect-timeout 3 http://httpbin.org/ip >/dev/null 2>&1; then
    echo "⚠️  代理不可达，将尝试直连"
    unset HTTP_PROXY
  else
    echo "❌ 网络连接异常, 建议检查网络或代理设置"
  fi
  echo ""
else
  echo ""
  echo "ℹ️ 未配置代理环境变量"
  echo ""
fi

mkdir -p "${DATA_DIR}"
export MOWER_DATA_DIR="${DATA_DIR}"

# 检测ADB路径
if [ ! -x "${ADB_BIN}" ]; then
  if command -v "${ADB_BIN}" >/dev/null 2>&1; then
    ADB_BIN="$(command -v "${ADB_BIN}")"
  elif command -v adb >/dev/null 2>&1; then
    ADB_BIN="$(command -v adb)"
  fi
fi

# 输出配置信息
echo "📂 数据目录: ${DATA_DIR}"
echo "🛠️ 使用的ADB: ${ADB_BIN}"
echo "🎮 模拟器目录: ${SIMULATOR_FOLDER}"
echo "🔑 webui token: ${TOKEN}"

# 如果MAA目录不存在或为空，则下载并解压最新版本
echo "🔍 检查MAA目录是否存在或为空..."
if [ ! -d "${MAA_DIR}" ] || [ -z "$(ls -A "${MAA_DIR}" 2>/dev/null)" ]; then
  echo "⬇️ 下载并安装最新版本的Maa..."
  url=$(curl -fsSL --connect-timeout 10 --max-time 30 https://api.github.com/repos/MaaAssistantArknights/MaaAssistantArknights/releases/latest \
    | jq -r --arg arch "${ARCH}" '[.assets[] | select(.name | contains("linux") and contains($arch) and contains("tar")) | .browser_download_url][0] // empty')
  if [ -z "${url}" ]; then
    echo "❌ 无法找到MaaAssistantArknights下载链接, 请检查网络连接或代理设置" >&2
    exit 1
  fi
  tmp_tar="/tmp/maa.tar.gz"
  echo "⬇️ 下载地址: ${url}"
  curl -L --no-buffer --progress-bar -o "${tmp_tar}" "${url}" 2>&1 | tr '\r' '\n' >&2
  if [ ! -f "${tmp_tar}" ]; then
    echo "❌ 下载失败, 如果持续出现此问题，您可以通过上方下载链接手动下载并解压到 ${MAA_DIR} 对应的文件夹中" >&2
    exit 1
  fi
  mkdir -p "${MAA_DIR}"
  tar -xzf "${tmp_tar}" -C "${MAA_DIR}"
  rm -f "${tmp_tar}"
  echo "✅ Maa已安装到${MAA_DIR}"
fi
echo ""

# 配置Mower
python - <<PY
from arknights_mower.utils import config
config.conf.maa_path = "${MAA_DIR}"
config.conf.maa_adb_path = "${ADB_BIN}"
config.conf.simulator.simulator_folder = "${SIMULATOR_FOLDER}"
config.conf.webview.token = "${TOKEN}"
config.conf.webview.port = int(${PORT})
config.conf.webview.tray = False
config.save_conf()
PY

echo "🚀 启动Mower服务, 端口: ${PORT}, Token: ${TOKEN}"
exec python -m flask --app server:app run --host=0.0.0.0 --port="${PORT}"
