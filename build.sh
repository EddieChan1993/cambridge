#!/usr/bin/env bash
# Build Cambridge.app
#
# 用法：
#   bash build.sh          完整打包（可分发的 .app，含所有依赖）
#   bash build.sh --dev    开发模式（符号链接，秒级完成，仅限本机调试）
set -e

DEV_MODE=false
for arg in "$@"; do
  case "$arg" in --dev|-dev|-d|–dev|—dev) DEV_MODE=true ;; esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

BUILD_LOG=$(mktemp /tmp/cambridge_build_XXXXXX.log)
trap 'rm -f "$BUILD_LOG"' EXIT

# ── 打印工具 ────────────────────────────────────────────────────────────────
_ok()   { printf "  \033[32m✓\033[0m  %s\n" "$*"; }
_step() { printf "  \033[34m→\033[0m  %s" "$*"; }
_done() { printf " \033[32mdone\033[0m\n"; }
_skip() { printf " \033[90mskipped\033[0m\n"; }
_fail() { printf " \033[31mfailed\033[0m\n"; }

echo ""
echo "  Cambridge Builder"
echo "  ──────────────────────────────────────────"

# ── 0. 关闭旧实例 ──────────────────────────────────────────────────────────
PID_FILE="$HOME/.cambridge_tool/app.pid"
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
        kill "$OLD_PID" 2>/dev/null || true
        sleep 0.5
        _ok "Killed old instance (PID $OLD_PID)"
    fi
    rm -f "$PID_FILE"
fi
pkill -x "Cambridge" 2>/dev/null || true

# 清除词条缓存
CACHE_FILE="$HOME/.cambridge_tool/cache.json"
if [ -f "$CACHE_FILE" ]; then
    rm -f "$CACHE_FILE"
    _ok "Cache cleared"
fi

# ── 1. 找 Python ──────────────────────────────────────────────────────────
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
    echo ""
    echo "  \033[31m✗\033[0m  找不到 Python 3.9+（非 Anaconda）。"
    echo "     请从 https://www.python.org 或 Homebrew 安装，然后重试。"
    exit 1
fi
_ok "Python $("$PYTHON" --version 2>&1 | awk '{print $2}')  ($PYTHON)"

# ── 2. 安装依赖 ───────────────────────────────────────────────────────────
REQ_HASH=$(md5 -q requirements.txt 2>/dev/null \
           || md5sum requirements.txt 2>/dev/null | awk '{print $1}')
PIP_FLAG=".cache_pip_${REQ_HASH}"

if [ ! -f "$PIP_FLAG" ]; then
    _step "Installing dependencies…"
    if "$PYTHON" -m pip install -r requirements.txt --quiet >>"$BUILD_LOG" 2>&1; then
        rm -f .cache_pip_*
        touch "$PIP_FLAG"
        _done
    else
        _fail
        echo ""; echo "── build log ──"; cat "$BUILD_LOG"; exit 1
    fi
else
    _ok "Dependencies up-to-date"
fi

# ── 3. Icon ───────────────────────────────────────────────────────────────
if [ -f icon.png ]; then
    ICON_HASH=$(md5 -q icon.png 2>/dev/null \
                || md5sum icon.png 2>/dev/null | awk '{print $1}')
    ICON_FLAG=".cache_icon_${ICON_HASH}"
    if [ ! -f "$ICON_FLAG" ]; then
        _step "Converting icon.png → icon.icns…"
        ICONSET="icon.iconset"
        rm -rf "$ICONSET" && mkdir "$ICONSET"
        for size in 16 32 64 128 256 512 1024; do
            sips -z $size $size icon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null 2>&1 || true
        done
        sips -z 32   32   icon.png --out "$ICONSET/icon_16x16@2x.png"   >/dev/null 2>&1 || true
        sips -z 64   64   icon.png --out "$ICONSET/icon_32x32@2x.png"   >/dev/null 2>&1 || true
        sips -z 256  256  icon.png --out "$ICONSET/icon_128x128@2x.png" >/dev/null 2>&1 || true
        sips -z 512  512  icon.png --out "$ICONSET/icon_256x256@2x.png" >/dev/null 2>&1 || true
        sips -z 1024 1024 icon.png --out "$ICONSET/icon_512x512@2x.png" >/dev/null 2>&1 || true
        iconutil -c icns "$ICONSET" -o icon.icns 2>>"$BUILD_LOG"
        rm -rf "$ICONSET"
        rm -f .cache_icon_*
        touch "$ICON_FLAG"
        _done
    else
        _ok "Icon unchanged"
    fi
fi

# ── 4. Build ──────────────────────────────────────────────────────────────
if $DEV_MODE; then
    _step "Building (dev / alias mode)… "
    rm -rf dist
    "$PYTHON" setup.py py2app --alias >>"$BUILD_LOG" 2>&1 &
    BUILD_PID=$!
    _START=$(date +%s)
    while kill -0 "$BUILD_PID" 2>/dev/null; do
        _ELAPSED=$(( $(date +%s) - _START ))
        printf "\r  \033[34m→\033[0m  Building (dev / alias mode)…  \033[90m%ds\033[0m " "$_ELAPSED"
        sleep 1
    done
    wait "$BUILD_PID" && _BUILD_OK=true || _BUILD_OK=false
    _ELAPSED=$(( $(date +%s) - _START ))
    if $_BUILD_OK; then
        printf "\r  \033[32m✓\033[0m  Building (dev / alias mode)…  \033[32mdone\033[0m (%ds)\n" "$_ELAPSED"
    else
        printf "\r  \033[31m✗\033[0m  Building (dev / alias mode)…  \033[31mfailed\033[0m (%ds)\n" "$_ELAPSED"
        echo ""; echo "── build log ──"
        grep -iE "(error|warning|exception|traceback)" "$BUILD_LOG" \
            | grep -v "DeprecatedInstaller\|fetch_build_eggs\|setuptools" || cat "$BUILD_LOG"
        exit 1
    fi

    echo "  ──────────────────────────────────────────"
    printf "  \033[32m✅  dist/Cambridge.app\033[0m  (dev build · local only)\n\n"
else
    _step "Cleaning previous build…"
    rm -rf build dist
    _done

    _step "Building (full / distributable)… "
    "$PYTHON" setup.py py2app >>"$BUILD_LOG" 2>&1 &
    BUILD_PID=$!
    _START=$(date +%s)
    while kill -0 "$BUILD_PID" 2>/dev/null; do
        _ELAPSED=$(( $(date +%s) - _START ))
        printf "\r  \033[34m→\033[0m  Building (full / distributable)…  \033[90m%ds\033[0m " "$_ELAPSED"
        sleep 1
    done
    wait "$BUILD_PID" && _BUILD_OK=true || _BUILD_OK=false
    _ELAPSED=$(( $(date +%s) - _START ))
    if $_BUILD_OK; then
        printf "\r  \033[32m✓\033[0m  Building (full / distributable)…  \033[32mdone\033[0m (%ds)\n" "$_ELAPSED"
    else
        printf "\r  \033[31m✗\033[0m  Building (full / distributable)…  \033[31mfailed\033[0m (%ds)\n" "$_ELAPSED"
        echo ""; echo "── build log ──"
        grep -iE "(error|warning|exception|traceback)" "$BUILD_LOG" \
            | grep -v "DeprecatedInstaller\|fetch_build_eggs\|setuptools" || cat "$BUILD_LOG"
        exit 1
    fi

    echo "  ──────────────────────────────────────────"
    printf "  \033[32m✅  dist/Cambridge.app\033[0m  (drag to /Applications to install)\n\n"
fi
