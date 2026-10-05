#!/bin/bash
set -e

# Setup and environment verification script
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "=== 环境检查与初始化 ==="

# 1. 检查 Python
if which python3 >/dev/null 2>&1; then
    echo "✓ Python: $(python3 --version)"
else
    echo "❌ 未检测到 Python 3，请先安装 Python 3.10+"
    exit 1
fi

# 2. 检查 Node.js / npm
if which node >/dev/null 2>&1; then
    echo "✓ Node.js: $(node --version)"
    echo "✓ npm: $(npm --version)"
else
    echo "❌ 未检测到 Node.js，请先安装 Node.js"
    exit 1
fi

# 3. 检查 FFmpeg
if [ -f "/opt/miniconda3/envs/mlscreen311/bin/ffmpeg" ]; then
    echo "✓ FFmpeg (Conda libass): /opt/miniconda3/envs/mlscreen311/bin/ffmpeg"
elif which ffmpeg >/dev/null 2>&1; then
    echo "✓ FFmpeg: $(which ffmpeg)"
else
    echo "⚠️ 未在 PATH 中找到 ffmpeg，可通过 Homebrew 安装: brew install ffmpeg"
fi

# 4. 安装 Python 依赖
VENV_DIR="${ROOT_DIR}/.venv"
PYTHON="${VENV_DIR}/bin/python"

if [ ! -d "${VENV_DIR}" ] || [ ! -x "${PYTHON}" ] || ! "${PYTHON}" -c "import sys" >/dev/null 2>&1; then
    echo "正在创建/重建 Python 虚拟环境..."
    rm -rf "${VENV_DIR}"
    SYS_PYTHON="python3"
    for candidate in python3.11 python3.12 python3.10 python3; do
        if which "${candidate}" >/dev/null 2>&1; then
            SYS_PYTHON="${candidate}"
            break
        fi
    done
    "${SYS_PYTHON}" -m venv "${VENV_DIR}"
fi

echo "正在安装 Python 依赖..."
"${VENV_DIR}/bin/pip" install --upgrade pip
"${VENV_DIR}/bin/pip" install -r "${ROOT_DIR}/backend/requirements.txt"

# 5. 安装前端依赖并构建
echo "正在安装前端依赖并构建静态资源..."
cd "${ROOT_DIR}/frontend"
npm install
npm run build

echo "=== 环境初始化完成！运行 bash scripts/run.sh 即可启动项目 ==="
