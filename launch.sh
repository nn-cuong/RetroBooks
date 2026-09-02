#!/bin/sh
case "$0" in
    */*) cd "${0%/*}" || exit 1 ;;
esac
APP_DIR="$(pwd)"

chmod +x "$APP_DIR/bin/"* 2>/dev/null
chmod +x "$APP_DIR/python/bin/"* 2>/dev/null

export LD_LIBRARY_PATH="$APP_DIR/python/lib:$APP_DIR:$LD_LIBRARY_PATH:/usr/trimui/lib:/mnt/SDCARD/System/lib"
export PYSDL2_DLL_PATH="/usr/trimui/lib"
export SDL_NOMOUSE=1

cd "$APP_DIR"

usable() {
    [ -n "$1" ] && [ -f "$1" ] || return 1
    [ -x "$1" ] || chmod +x "$1" 2>/dev/null
    "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null
}

PY=""
# 1. Bundled Python in App (Standalone 100%)
if usable "$APP_DIR/python/bin/python3"; then
    PY="$APP_DIR/python/bin/python3"
    export PYTHONHOME="$APP_DIR/python"
    export PYTHONPATH="$APP_DIR/python/lib/python3.11:$APP_DIR/vendor:$APP_DIR"
fi

# 2. Fallback to System Python
if [ -z "$PY" ]; then
    for c in "/mnt/SDCARD/System/bin/python3" "/usr/bin/python3"; do
        if usable "$c"; then
            PY="$c"
            break
        fi
    done
fi

if [ -z "$PY" ]; then
    SYS_PY=$(command -v python3)
    if usable "$SYS_PY"; then
        PY="$SYS_PY"
    fi
fi

if [ -z "$PY" ]; then
    echo "Cannot find a valid Python3 interpreter" > "$APP_DIR/crash.log"
    exit 1
fi

"$PY" main.py > "$APP_DIR/crash.log" 2>&1

