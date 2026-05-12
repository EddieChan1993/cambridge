#!/usr/bin/env bash
# Build Cambridge.app
#
# 用法：
#   bash build.sh          完整打包（可分发的 .app，含所有依赖）
#   bash build.sh --dev    开发模式（符号链接，秒级完成，仅限本机调试）
set -e

DEV_MODE=false
for arg in "$@"; do
  [ "$arg" = "--dev" ] && DEV_MODE=true
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# ── 0. 关闭正在运行的旧版本 ────────────────────────────────────────────────
PID_FILE="$HOME/.cambridge_tool/app.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        echo "==> 关闭正在运行的旧版本 (PID $OLD_PID)…"
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.5
    fi
    rm -f "$PID_FILE"
fi
# 兜底：按名字杀，防止 pid 文件丢失但进程还在
pkill -x "Cambridge" 2>/dev/null || true

# 清除词条缓存（代码变更后保证拿到新格式数据）
CACHE_FILE="$HOME/.cambridge_tool/cache.json"
if [ -f "$CACHE_FILE" ]; then
    rm -f "$CACHE_FILE"
    echo "==> 词条缓存已清除。"
fi

# ── 1. 找到合适的 Python（3.9+，非 Anaconda）─────────────────────────────
_find_python() {
    for candidate in \
        /usr/local/bin/python3.12 \
        /usr/local/bin/python3.11 \
        /usr/local/bin/python3.10 \
        /usr/local/bin/python3.9 \
        /opt/homebrew/bin/python3.12 \
        /opt/homebrew/bin/python3.11 \
        /opt/homebrew/bin/python3.10 \
        /opt/homebrew/bin/python3.9 \
        /usr/bin/python3
    do
        [ -x "$candidate" ] || continue
        case "$candidate" in *anaconda*|*conda*|*miniforge*) continue ;; esac
        ok=$("$candidate" -c \
            "import sys; print('ok' if sys.version_info>=(3,9) else 'no')" 2>/dev/null || echo "no")
        [ "$ok" = "ok" ] && { echo "$candidate"; return; }
    done
    echo ""
}

PYTHON=$(_find_python)
if [ -z "$PYTHON" ]; then
    echo "❌  找不到 Python 3.9+（非 Anaconda）。"
    echo "    请从 https://www.python.org 或 Homebrew 安装 Python 3.9+，然后重试。"
    exit 1
fi
echo "==> 使用 Python: $PYTHON  ($("$PYTHON" --version))"

# ── 2. Python 依赖（pip）────────────────────────────────────────────────────
REQ_HASH=$(md5 -q requirements.txt 2>/dev/null \
           || md5sum requirements.txt 2>/dev/null | awk '{print $1}')
PIP_FLAG=".cache_pip_${REQ_HASH}"

if [ ! -f "$PIP_FLAG" ]; then
    echo "==> Installing Python dependencies…"
    "$PYTHON" -m pip install -r requirements.txt --quiet
    rm -f .cache_pip_*
    touch "$PIP_FLAG"
else
    echo "==> Python dependencies up-to-date (skipping pip install)."
fi

# ── 3. Icon conversion ──────────────────────────────────────────────────────
if [ -f icon.png ]; then
    ICON_HASH=$(md5 -q icon.png 2>/dev/null \
                || md5sum icon.png 2>/dev/null | awk '{print $1}')
    ICON_FLAG=".cache_icon_${ICON_HASH}"
    if [ ! -f "$ICON_FLAG" ]; then
        echo "==> Converting icon.png → icon.icns…"
        ICONSET="icon.iconset"
        rm -rf "$ICONSET"
        mkdir "$ICONSET"
        sips -z 16   16   icon.png --out "$ICONSET/icon_16x16.png"      >/dev/null
        sips -z 32   32   icon.png --out "$ICONSET/icon_16x16@2x.png"   >/dev/null
        sips -z 32   32   icon.png --out "$ICONSET/icon_32x32.png"      >/dev/null
        sips -z 64   64   icon.png --out "$ICONSET/icon_32x32@2x.png"   >/dev/null
        sips -z 128  128  icon.png --out "$ICONSET/icon_128x128.png"    >/dev/null
        sips -z 256  256  icon.png --out "$ICONSET/icon_128x128@2x.png" >/dev/null
        sips -z 256  256  icon.png --out "$ICONSET/icon_256x256.png"    >/dev/null
        sips -z 512  512  icon.png --out "$ICONSET/icon_256x256@2x.png" >/dev/null
        sips -z 512  512  icon.png --out "$ICONSET/icon_512x512.png"    >/dev/null
        sips -z 1024 1024 icon.png --out "$ICONSET/icon_512x512@2x.png" >/dev/null
        iconutil -c icns "$ICONSET" -o icon.icns
        rm -rf "$ICONSET"
        rm -f .cache_icon_*
        touch "$ICON_FLAG"
        echo "    icon.icns created."
    else
        echo "==> icon.png unchanged, reusing icon.icns."
    fi
else
    echo "==> No icon.png found; app will use default macOS icon."
fi

# ── 4. Build ────────────────────────────────────────────────────────────────
if $DEV_MODE; then
    # 开发模式：alias 模式，只建符号链接，不复制不签名，几秒完成
    echo "==> [开发模式] Running py2app --alias…"
    rm -rf dist
    "$PYTHON" setup.py py2app --alias 2>&1 \
        | grep -v "replacing existing signature" \
        | grep -v "^$"

    if [ -d "dist/Cambridge.app" ]; then
        echo ""
        echo "✅  Dev build: dist/Cambridge.app"
        echo "    （仅限本机，不可分发）"
    else
        echo "❌  Dev build failed."; exit 1
    fi
else
    # 完整打包：清理旧产物，重新打包
    echo "==> Cleaning previous build artefacts…"
    rm -rf build dist

    echo "==> Running py2app…"
    "$PYTHON" setup.py py2app 2>&1 \
        | grep -v "replacing existing signature" \
        | grep -v "^$"

    if [ -d "dist/Cambridge.app" ]; then
        echo ""
        echo "✅  Build succeeded: dist/Cambridge.app"
        echo "    拖入 /Applications 即可使用。"
    else
        echo "❌  Build failed — check output above."; exit 1
    fi
fi
