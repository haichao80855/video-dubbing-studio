#!/bin/bash
set -e

# Video Dubbing System (Bilibili/YouTube -> 中文 MP4)
# One-click startup script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

echo "=========================================================="
echo "🎬 Video Dubbing Studio - 启动中..."
echo "=========================================================="

cd "${ROOT_DIR}"

# 1. Check Python virtual environment (Auto-detect broken or copied venvs)
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"

if [ ! -d "${VENV_DIR}" ] || [ ! -x "${PYTHON}" ] || ! "${PYTHON}" -c "import sys" >/dev/null 2>&1; then
  echo "⚠️ 检测到虚拟环境不存在或跨机器拷贝导致路径失效，正在为当前 Mac 重建 .venv..."
  rm -rf "${VENV_DIR}"

  # Discover best python (prefer python3.11, python3.12, python3.10, python3)
  SYS_PYTHON=""
  for candidate in python3.11 python3.12 python3.10 python3 /opt/homebrew/bin/python3.11 /usr/local/bin/python3.11; do
    if which "${candidate}" >/dev/null 2>&1 || [ -x "${candidate}" ]; then
      SYS_PYTHON="${candidate}"
      break
    fi
  done

  if [ -z "${SYS_PYTHON}" ]; then
    echo "❌ 未检测到 Python 3，请先安装 Python 3.10+: brew install python@3.11"
    exit 1
  fi

  echo "🐍 使用系统 Python: $(${SYS_PYTHON} --version) 创建虚拟环境..."
  "${SYS_PYTHON}" -m venv "${VENV_DIR}"
  "${VENV_DIR}/bin/pip" install --upgrade pip
  echo "📦 正在安装依赖包 (首次需要几分钟)..."
  "${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt"
  echo "✓ 依赖安装完成！"
fi

# 2. Check and rebuild frontend if needed
echo "📦 检查并构建前端静态资源..."
cd "${ROOT_DIR}/frontend"
npm run build
cd "${ROOT_DIR}"

# 3. Kill any zombie process holding port 8000 to guarantee newest code runs
if lsof -ti :8000 >/dev/null 2>&1; then
  echo "🔄 清理占用 8000 端口的旧进程，确保加载最新代码..."
  lsof -ti :8000 | xargs kill -9 2>/dev/null || true
  sleep 0.5
fi

# 3. Handle arguments: --dev runs both backend and vite dev server
if [ "$1" == "--dev" ]; then
  echo "🚀 启动开发模式 (FastAPI: 8000, Vite Dev Server: 5173)..."
  "${PYTHON}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000 --reload &
  BACKEND_PID=$!
  cd "${ROOT_DIR}/frontend"
  npm run dev &
  FRONTEND_PID=$!
  
  trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
  wait
else
  echo "🚀 启动生产服务 (前后端一体化运行在 http://127.0.0.1:8000)..."
  echo "💡 提示：在浏览器打开 http://127.0.0.1:8000 即可使用"
  
  # Open browser automatically on macOS
  (sleep 1.5 && which open >/dev/null && open "http://127.0.0.1:8000") &

  "${PYTHON}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
fi
